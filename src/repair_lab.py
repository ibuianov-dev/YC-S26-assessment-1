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


def _collapse_page(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse rows that name the same company.

    The uploaded list can name a company more than once, so the page is
    reduced to one row per company before anything downstream sees it.
    """
    kept: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        company_id = str(row["company_id"])
        if company_id in seen:
            continue
        seen.add(company_id)
        kept.append(row)
    return kept


def _make_deliverables(
    accounts: list[dict[str, Any]],
    *,
    brand_kit_id: str,
    template_id: str,
) -> list[dict[str, str]]:
    deliverables: list[dict[str, str]] = []
    for account in accounts:
        effective_brand_kit = str(
            account.get("saved_brand_kit_id", brand_kit_id)
        )
        effective_template = str(
            account.get("saved_template_id", template_id)
        )
        for asset_type in REQUIRED_ASSET_TYPES:
            deliverables.append(
                {
                    "source_row_id": str(account["id"]),
                    "company_id": str(account["company_id"]),
                    "company_name": str(account["company_name"]),
                    "asset_type": asset_type,
                    "brand_kit_id": effective_brand_kit,
                    "template_id": effective_template,
                }
            )
    return deliverables


def build_campaign_plan(
    tool: AccountPageLoader,
    *,
    brand_kit_id: str,
    template_id: str,
    page_size: int = 25,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    cursor: str | None = None
    while True:
        page = tool.load_page(cursor=cursor, page_size=page_size)
        rows.extend(_collapse_page(page.rows))
        if not page.truncated:
            break
        cursor = page.next_cursor

    return {
        "source_row_ids": [str(row["id"]) for row in rows],
        "deliverables": _make_deliverables(
            rows,
            brand_kit_id=brand_kit_id,
            template_id=template_id,
        ),
        # The brand kit/template actually requested, so a coverage check can
        # tell "built with what was asked for" from "built with something
        # else" without having to be handed the request separately.
        "brand_kit_id": brand_kit_id,
        "template_id": template_id,
        "complete": True,
    }


def evaluate_campaign_coverage(
    plan: dict[str, Any],
    accounts: list[dict[str, Any]],
) -> tuple[bool, str]:
    """Strict coverage check, verified against the uploaded accounts.

    Unlike the original check, this does not just ask the plan whether it
    agrees with itself. It rebuilds the set of companies the upload actually
    requires and requires the plan to match it exactly:

    - every real company_id in the upload must appear in the plan. Rows
      sharing a company_id collapse into one expected company, same as the
      builder does.
    - a row with a missing/null company_id can never be merged with any
      other row - each one is its own unresolved entity, keyed by its own
      source_row_id, and must be accounted for on its own.
    - each expected entity must have exactly the four required asset types,
      no duplicates and nothing missing.
    - every deliverable for that entity must carry the brand kit and
      template actually requested on this campaign - a saved per-account
      preference from a previous campaign does not override what the
      customer selected this time.
    """
    deliverables = plan.get("deliverables", [])
    expected_brand_kit = plan.get("brand_kit_id")
    expected_template = plan.get("template_id")
    if expected_brand_kit is None or expected_template is None:
        return False, "plan does not record which brand kit/template were requested"

    def entity_key(company_id: Any, source_row_id: Any) -> str:
        if company_id is None:
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
