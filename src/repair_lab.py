from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


REQUIRED_ASSET_TYPES = (
    "landing_page",
    "linkedin_ad_1",
    "linkedin_ad_2",
    "linkedin_ad_3",
)


@dataclass(frozen=True)
class ToolPage:
    rows: list[dict[str, Any]]
    next_cursor: str | None
    truncated: bool


class AccountPageLoader(Protocol):
    def load_page(
        self,
        *,
        cursor: str | None = None,
        page_size: int = 25,
    ) -> ToolPage: ...


class TargetAccountTool:
    """Deterministic stand-in for the paginated uploaded-account service."""

    def __init__(self, accounts: list[dict[str, Any]]) -> None:
        self._accounts = [dict(account) for account in accounts]

    def load_page(
        self,
        *,
        cursor: str | None = None,
        page_size: int = 25,
    ) -> ToolPage:
        start = int(cursor or "0")
        rows = self._accounts[start : start + page_size]
        next_index = start + len(rows)
        next_cursor = (
            str(next_index) if next_index < len(self._accounts) else None
        )
        return ToolPage(
            rows=rows,
            next_cursor=next_cursor,
            truncated=next_cursor is not None,
        )


def _entity_key(row: dict[str, Any]) -> str:
    """Identity used to decide whether two rows name the same thing.

    Rows sharing a real company_id collapse into one. A missing or blank
    company_id is never assumed to match another missing/blank one, so
    it's keyed by the row's own id instead.
    """
    company_id = row.get("company_id")
    if not company_id:
        return f"unresolved:{row['id']}"
    return f"company:{company_id}"


def _dedupe_rows(
    rows: list[dict[str, Any]], seen: set[str]
) -> list[dict[str, Any]]:
    """Drop rows already kept, across every page of this read (`seen` is
    shared across the whole `build_campaign_plan` call)."""
    kept: list[dict[str, Any]] = []
    for row in rows:
        key = _entity_key(row)
        if key in seen:
            continue
        seen.add(key)
        kept.append(row)
    return kept


def _make_deliverables(
    accounts: list[dict[str, Any]],
    *,
    brand_kit_id: str,
    template_id: str,
) -> list[dict[str, str]]:
    """Build the four required assets for each account, using the brand
    kit/template selected on *this* request (never a saved one from an
    earlier campaign)."""
    deliverables: list[dict[str, Any]] = []
    for account in accounts:
        company_id = account.get("company_id")
        for asset_type in REQUIRED_ASSET_TYPES:
            deliverables.append(
                {
                    "source_row_id": str(account["id"]),
                    "company_id": str(company_id) if company_id is not None else None,
                    "company_name": str(account["company_name"]),
                    "asset_type": asset_type,
                    "brand_kit_id": brand_kit_id,
                    "template_id": template_id,
                }
            )
    return deliverables


class PaginationStalledError(RuntimeError):
    """Raised when the account service stops making real progress (frozen
    or cycling cursor, or a page claiming more data with no way to reach
    it). We refuse to publish a partial or looping plan."""


MAX_PAGE_FETCHES = 500
# One page is allowed to come back twice in a row (an upstream retry
# replaying the same response) without it counting as stalled. A third
# time asking for the same cursor is not a retry anymore.
MAX_CURSOR_REPEATS = 2


def build_campaign_plan(
    tool: AccountPageLoader,
    *,
    brand_kit_id: str,
    template_id: str,
    page_size: int = 25,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    seen_entities: set[str] = set()
    cursor_uses: dict[str, int] = {}
    cursor: str | None = None
    fetches = 0

    while True:
        fetches += 1
        if fetches > MAX_PAGE_FETCHES:
            raise PaginationStalledError(
                f"account service had not finished after {MAX_PAGE_FETCHES} "
                "page fetches; refusing to publish a plan that may be "
                "incomplete or looping"
            )

        cursor_token = cursor if cursor is not None else "<start>"
        cursor_uses[cursor_token] = cursor_uses.get(cursor_token, 0) + 1
        if cursor_uses[cursor_token] > MAX_CURSOR_REPEATS:
            raise PaginationStalledError(
                f"account service returned cursor {cursor_token!r} "
                f"{cursor_uses[cursor_token]} times without making "
                "progress; refusing to loop forever"
            )

        page = tool.load_page(cursor=cursor, page_size=page_size)
        rows.extend(_dedupe_rows(page.rows, seen_entities))

        if not page.truncated:
            break

        if page.next_cursor is None:
            raise PaginationStalledError(
                "account service reported more data (truncated=True) but "
                "supplied no cursor to continue from"
            )
        cursor = page.next_cursor

    return {
        "source_row_ids": [str(row["id"]) for row in rows],
        "deliverables": _make_deliverables(
            rows,
            brand_kit_id=brand_kit_id,
            template_id=template_id,
        ),
        # Recorded so coverage checks can verify against what was requested.
        "brand_kit_id": brand_kit_id,
        "template_id": template_id,
        "complete": True,
    }


def evaluate_campaign_coverage(
    plan: dict[str, Any],
    accounts: list[dict[str, Any]],
) -> tuple[bool, str]:
    """Strict coverage check, verified against the uploaded accounts rather
    than just asking the plan whether it agrees with itself.

    Requires: every expected entity (same company_id/unresolved-row keying
    as the builder) is present with exactly the 4 required asset types and
    the brand kit/template actually requested on this campaign.
    """
    deliverables = plan.get("deliverables", [])
    expected_brand_kit = plan.get("brand_kit_id")
    expected_template = plan.get("template_id")
    if expected_brand_kit is None or expected_template is None:
        return False, "plan does not record which brand kit/template were requested"

    def entity_key(company_id: Any, source_row_id: Any) -> str:
        if not company_id:
            return f"unresolved:{source_row_id}"
        return f"company:{company_id}"

    expected_entities = {
        entity_key(account.get("company_id"), account["id"]) for account in accounts
    }

    by_entity: dict[str, list[dict[str, Any]]] = {}
    for item in deliverables:
        key = entity_key(item.get("company_id"), item.get("source_row_id"))
        by_entity.setdefault(key, []).append(item)

    missing = expected_entities - by_entity.keys()
    if missing:
        example = sorted(missing)[0]
        return False, f"{len(missing)} expected companies missing from the plan, e.g. {example}"

    extra = by_entity.keys() - expected_entities
    if extra:
        example = sorted(extra)[0]
        return False, f"plan contains {len(extra)} entities not in the uploaded list, e.g. {example}"

    for key, items in sorted(by_entity.items()):
        asset_types = [str(item.get("asset_type")) for item in items]
        if (
            len(items) != len(REQUIRED_ASSET_TYPES)
            or set(asset_types) != set(REQUIRED_ASSET_TYPES)
            or len(set(asset_types)) != len(asset_types)
        ):
            return False, f"{key} has {len(items)} deliverables instead of exactly the 4 required asset types"
        for item in items:
            if str(item.get("brand_kit_id")) != str(expected_brand_kit):
                return False, f"{key} was built with the wrong brand kit ({item.get('brand_kit_id')!r})"
            if str(item.get("template_id")) != str(expected_template):
                return False, f"{key} was built with the wrong template ({item.get('template_id')!r})"

    if plan.get("complete") is not True:
        return False, "campaign did not declare completion"

    return True, f"all {len(expected_entities)} expected companies have exactly the requested assets, brand kit, and template"
