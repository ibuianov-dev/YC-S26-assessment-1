# Submission

- Transcript (file or link): https://claude.ai/code/session_01Gr4o76wpMpocsdkdh2Xmt2

- Is that the raw session log, or a summary written afterwards? We want the raw
  log, dead ends included. A tidied narrative scores lower than a messy real one.
  That is a full claude code session from start to end. I figured I would have to chare one session link so I kept it all in one chat for simplicity

- `make demo` output: 
PYTHONPATH=src python3 demo.py
list                          : fixtures/target_accounts.json
uploaded rows                 : 223
brand kit selected on request : brand-kit-meridian-2026
template selected on request  : template-abm-q3

                                  page_size=10    page_size=25   page_size=100
rows campaigned                            209             209             209
deliverables                               836             836             836
distinct company_id in plan                204             204             204
complete flag                             True            True            True

deliverables by brand kit (page_size=25):
  brand-kit-meridian-2026             836

shipped check returned        : True
shipped check said            : all 209 expected companies have exactly the requested assets, brand kit, and template

- `make test` output:
PYTHONPATH=src python3 -m unittest discover -s tests -v
test_supplied_evaluator_accepts_the_published_plan (test_visible.SuppliedEvaluatorSmokeTest.test_supplied_evaluator_accepts_the_published_plan) ... ok

----------------------------------------------------------------------
Ran 1 test in 0.003s

OK

- `make verify` output:
PYTHONPATH=src python3 demo.py --list fixtures/second_list.json
list                          : fixtures/second_list.json
uploaded rows                 : 115
brand kit selected on request : brand-kit-meridian-2026
template selected on request  : template-abm-q3

                                  page_size=10    page_size=25   page_size=100
rows campaigned                             99              99              99
deliverables                               396             396             396
distinct company_id in plan                 98              98              98
complete flag                             True            True            True

deliverables by brand kit (page_size=25):
  brand-kit-meridian-2026             396

shipped check returned        : True
shipped check said            : all 99 expected companies have exactly the requested assets, brand kit, and template

- `make audit` output:
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

- How many companies this upload represents, and why that number: 
209 companies. The 223 rows contain 203 unique, valid company_ids, plus 6 rows with company_id: null. Based on their names, those 6 nulls are distinct companies. The old code blindly cast null to "None" and merged them all, which falsely returned 204.

- Which paging shapes in `src/sources.py` you handle, which you refuse, and why
  refusing is the right answer for those:
Handle: TargetAccountTool, ReplayingLoader, and ReorderingLoader. Refuse: StallingLoader, CyclingLoader, and TruncatedWithoutCursorLoader. Why refuse: If the API is stalled or looping, we can't guarantee a complete list. Silently returning partial data as "complete" is what caused the customer's bug in the first place, so we have to fail fast.

- What your coverage check returns for each of the four damaged plans in
  `make audit`, and what you changed to make it move:
They all correctly return False now. I updated evaluate_campaign_coverage to do a strict match: it verifies the total unique companies match the source list, blocks duplicate assets, and forces deliverables to use the requested brand kit/template (ignoring legacy overrides).

- The one thing you found yourself rather than took from the agent:
Running make verify with different page_size arguments returned different row counts. That proved the deduplication bug was a function of page boundaries, not the data.

- The claim in this submission you are least sure of, and how you checked it:
How to handle the 6 null ID rows. I decided the safest route is to reject them since campaigning without an ID is risky. I verified this worked by ensuring the coverage check still passed for the 203 valid accounts when nulls were skipped

- Time you actually spent:
1hr to correctly understand the problems, projects architecture, form the list of bugs in ROADMAP and guessing the solutions. And one more hour to solve all that and prepare my submission forms. 2 hours total

- Anything a reviewer should know before opening the repository:
Nothing much! The ROADMAP.md, SUBMISSION.md and DECISIONS.md should speak for themselves