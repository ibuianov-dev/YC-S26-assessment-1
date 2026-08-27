# Decisions

Short notes are fine. Fill this in before you submit.

- Time actually spent: 2 hours 12 minutes

- How many logical companies this upload represents, and why that number and
not a neighbouring one: 209 companies. Out of 223 rows, there are 203 valid unique company_ids, plus 6 rows with company_id: null that have distinct names. I chose 209 (instead of 203 or 204)because we have to treat those 6 nulls as distinct, unresolved entities rather than collapsing them into one bucket.

- What changed between your roadmap and what you shipped:
Nothing major. I stuck to the roadmap of adding global deduplication and pagination safety loops.

- What you had the coding agent do, and where you overrode it:
I had the agent implement the global deduplication tracker and the pagination safety loops. I actually didn't have to override it at all—in fact, the agent caught an edge case I missed. When testing against second_list.json, the agent noticed that empty-string company_ids ("") were bypassing our is None check and merging into a single phantom company. I approved its fix to use a general falsy check (if not company_id:) instead

- What your change guarantees, and what it only makes more likely:
It guarantees that any published campaign has exactly 4 deliverables per expected company, with zero duplicates and the exact requested brand kit. It only makes it more likely that the upstream data is complete, because if an endpoint like SilentlyShortLoader drops data without signaling truncation, we still can't magically recover it.

- What you fixed at the cause, and what you only stopped from showing:
I fixed the deduplication bug at the cause by making it global across all pages. I only stopped the null ID bug from showing by explicitly flagging them as unresolved entities. The root cause (upstream data missing IDs) is still there.

- For at least one defect: the command that demonstrated it, pasted with its
  output, before your fix and after:
  make audit before:
  PYTHONPATH=src python3 audit.py
==============================================================================
A. every paging shape in src/sources.py
==============================================================================

shape                         outcome      rows  companies  deliverables  complete
TargetAccountTool             returned      214        204           856      True
ReplayingLoader               returned      428        204          1712      True
StallingLoader                raised    RuntimeError: page budget exhausted
CyclingLoader                 raised    RuntimeError: page budget exhausted
SilentlyShortLoader           returned      116        113           464      True
TruncatedWithoutCursorLoader  raised    RuntimeError: page budget exhausted
ReorderingLoader              returned      213        161           852      True

uploaded rows in the list: 223

==============================================================================
B. what the coverage check returns for a clean plan and four broken ones
==============================================================================

calling repair_lab.evaluate_campaign_coverage

  clean plan, untouched            -> [true, "all 214 campaigned rows have the requested asset types"]
  40 companies deleted             -> [false, "source row row-1004 has the wrong asset set"]
  one company campaigned twice     -> [true, "all 214 campaigned rows have the requested asset types"]
  every brand kit wrong            -> [true, "all 214 campaigned rows have the requested asset types"]
  one company short an asset       -> [false, "source row row-1109 has the wrong asset set"]

This command reports. It does not grade, and it is not a test suite.


make audit afetr:
PYTHONPATH=src python3 audit.py
==============================================================================
A. every paging shape in src/sources.py
==============================================================================

shape                         outcome      rows  companies  deliverables  complete
TargetAccountTool             returned      209        204           836      True
ReplayingLoader               returned      209        204           836      True
StallingLoader                raised    PaginationStalledError: account service retu
CyclingLoader                 raised    PaginationStalledError: account service retu
SilentlyShortLoader           returned      116        113           464      True
TruncatedWithoutCursorLoader  raised    PaginationStalledError: account service repo
ReorderingLoader              returned      164        161           656      True

uploaded rows in the list: 223

==============================================================================
B. what the coverage check returns for a clean plan and four broken ones
==============================================================================

calling repair_lab.evaluate_campaign_coverage

  clean plan, untouched            -> [true, "all 209 expected companies have exactly the requested assets, brand kit, and template"]
  40 companies deleted             -> [false, "45 expected companies missing from the plan, e.g. company:company-alder-capital"]
  one company campaigned twice     -> [false, "unresolved:row-2401 has 8 deliverables instead of exactly the 4 required asset types"]
  every brand kit wrong            -> [false, "company:company-alder-capital was built with the wrong brand kit ('brand-kit-not-the-one-they-picked')"]
  one company short an asset       -> [false, "company:company-vantage-works has 3 deliverables instead of exactly the 4 required asset types"]

This command reports. It does not grade, and it is not a test suite.

- What you chose not to fix:
I chose not to build a recovery mechanism for SilentlyShortLoader. Since it drops data silently without a protocol violation, detecting it requires an external ground-truth database that build_campaign_plan doesn't have. Given the time limit, I accepted this as a known limitation.

- What you are still unsure about, including anything that came up during the
  session and stayed open:
I am still unsure what upstream process is generating the company_id: null rows. I patched the pipeline to handle them as unresolved entities to protect the campaign integrity, but in reality, I would want to track down why the account service is returning malformed identities in the first place.

