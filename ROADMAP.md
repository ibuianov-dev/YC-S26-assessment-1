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