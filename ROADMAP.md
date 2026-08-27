# Roadmap

## General Objective
Make the compaign generation and verification system handle the incomplete customer data 

## Initial findings
I ran the make audit, make verify and make test commands to see the the general picture of outputs and saw the inconsistency data right away in different places. There are several reasons for this:
- The script checks and caches duplicates but only on page level so same companies on different pages are treated as different companies.
- The system process API retries like in ReplayingLoader as brand new pages. Thats why we get twice as much deliverables and rows for ReplayingLoader for the same number of companies.
- Some companies had company_id of null because literal dudupe key "None" is treated as they were six instances of one company
---

build_campaign_plan sets "complete": True unconditionally, with no relationship to how the paging actually went. It's not derived from anything — it's just always True. Worth naming as its own root cause, since it's the reason SilentlyShortLoader (and in principle any partial read) reports success.

---
StallingLoader, CyclingLoader and TruncatedWithoutCursorLoader all raise an error saying 'page budget exhausted'. After examining the implementation we can say that:
- StallingLoader freezes on cursor 50 forever abd keeps returning next_cursor="50"
- CyclingLoader wraps around to 0 and stars over which leads to an infinite loop
- TruncatedWithoutCursorLoader returns trancated=True correctly indicating theres more data. however the next_cusor=None makes the loop to fetch page 1 forever

These are the reasons it only stops rasing an error. Otherwise it would be an infinite loop.

## Fix plan

1. Make `evaluate_campaign_coverage` strict, checked against the ground-truth
   account list (not just the plan checking itself):
   - fail if any expected company is missing from the plan's deliverables.
     This requires first deciding what "expected company" means for the 6
     rows with `company_id: null` — treat each as its own unresolved entry
     that must be explicitly flagged/refused rather than silently merged
     into one bucket or dropped.
   - fail if any deliverable's `brand_kit_id`/`template_id` doesn't match
     what the customer selected on the request.
   - fail if any company has duplicate deliverables, or anything other than
     exactly 4 assets.
   - this is also what catches `ReorderingLoader`: it never stalls or
     repeats a cursor, so nothing in step 2 sees it — the only signal that
     it dropped/duplicated rows is the final company set coming up short
     against the ground-truth list.

2. Fix `build_campaign_plan`'s reader:
   - replace page-level dedup with global dedup (seen company_ids tracked
     across the whole read, not reset per page).
   - track seen cursors and cap total page fetches; if a cursor repeats or
     the budget is exceeded, fail fast instead of looping (catches
     `StallingLoader`, `CyclingLoader`).
   - explicitly handle `truncated=True` with `next_cursor=None` as a
     protocol violation — refuse immediately rather than re-fetching page
     one forever (catches `TruncatedWithoutCursorLoader`).
   - derive `complete` from whether the read actually finished cleanly,
     instead of hardcoding `True`.

3. Re-run `make verify` (and `make audit`) against both fixture lists to
   confirm the fixes generalize and aren't fit to one file.
