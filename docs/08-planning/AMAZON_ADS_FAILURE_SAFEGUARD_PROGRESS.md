# Amazon Ads Failure Safeguard Progress

This tracker preserves the full safeguard scope from the Sponsored Products Search Term Report review and records implementation progress. Status values: `todo`, `in_progress`, `implemented`, `documented`.

## Progress Summary
| Area | Status | Implementation notes |
| --- | --- | --- |
| File upload and format problems | implemented | Parser and report detector cover file type, aliases, hidden spaces, Excel dates, required columns, and report type warnings. Safeguards now emit explicit review codes for hidden header spaces, alias normalization, numeric/percentage format problems, duplicate rows, date ranges, marketplace, and currency. |
| Metric calculation mistakes | in_progress | Monitoring metrics calculate CTR, CPC, CVR, ACOS, ROAS deterministically; safeguards compare uploaded Amazon metrics to recalculated values. |
| Search term interpretation mistakes | in_progress | Safeguards classify ASIN-like search terms, auto/product-targeting contexts, missing match type, product-specific and match-type duplicate behavior. |
| Campaign creation mistakes | in_progress | Existing campaign rules require approved keyword sets and human approval. Remaining safety enhancements include margin/data thresholds and duplicate campaign checks. |
| Negative keyword mistakes | in_progress | Existing monitoring rules require click/order thresholds and human approval. Safeguards flag converting terms and match-type risks. |
| Monitoring and optimization mistakes | in_progress | Existing monitoring rules use thresholds and no-live-change boundaries. Safeguards add zero-sales spend, data reliability, attribution-window, and margin-risk warnings. |
| Analyst confusion scenarios | documented | Captured as risk explanations and labels for user-facing review. |
| Money-waste danger zones | documented | Captured as risk labels and implementation acceptance criteria. |
| Required safeguards | in_progress | Validation, metric comparison, minimum-data rules, human checkpoints, and risk labels are being implemented incrementally. |

## 1. File Upload And Format Problems
| # | Scenario | Status | Safeguard |
| --- | --- | --- | --- |
| 1 | Wrong file type uploaded: search term, targeting, campaign, advertised product, placement, competitor export, wrong marketplace/account. | implemented | `ReportTypeDetector` classifies known report types and records missing required columns. |
| 2 | Amazon column names change: 7-day/14-day sales, ACOS, Spend/Cost, Customer Search Term/Search Term. | implemented | Header aliases map common metric/report variants to canonical report detection and safeguard columns. |
| 3 | Hidden spaces in column names. | implemented | Parser strips headers and now preserves duplicate stripped headers with suffixes instead of overwriting data. |
| 4 | Excel dates read as serial numbers such as `46139`. | implemented | Parser converts styled date cells and date-named numeric columns to ISO dates. |
| 5 | Currency mismatch: USD, GBP, CAD, mixed marketplaces, assumed USD budgets. | implemented | Safeguards flag unexpected or mixed currencies. |
| 6 | Marketplace mismatch: United States vs UK, Germany, UAE, Canada, mixed countries. | implemented | Safeguards flag unexpected or mixed retailer/country values. |
| 7 | Duplicate rows across campaigns, ad groups, match types, dates, ASINs/products. | implemented | Safeguards detect duplicate search terms across product, match-type, target, ad group, and campaign keys. |
| 8 | Empty/null/zero values, especially blank ACOS when sales are zero. | implemented | Monitoring keeps ACOS null when sales are zero; safeguards label spend-with-no-sales risk. |

## 2. Metric Calculation Mistakes
| # | Scenario | Status | Safeguard |
| --- | --- | --- | --- |
| 9 | ACOS calculated incorrectly. | implemented | Deterministic `Spend / Sales` recalculation and mismatch warnings. |
| 10 | ROAS calculated incorrectly. | implemented | Deterministic `Sales / Spend` recalculation and mismatch warnings. |
| 11 | Conversion rate calculated incorrectly. | implemented | Deterministic `Orders / Clicks` recalculation and mismatch warnings. |
| 12 | CTR calculated incorrectly. | implemented | Deterministic `Clicks / Impressions` recalculation and mismatch warnings. |
| 13 | CPC misunderstood. | implemented | Deterministic `Spend / Clicks` recalculation and evidence fields. |
| 14 | Orders vs units confusion. | implemented | Safeguards flag units/orders divergence for analyst review. |
| 15 | Total sales vs advertised SKU sales vs other SKU sales confusion. | implemented | Safeguards flag rows where other-SKU sales dominate total sales. |

## 3. Search Term Interpretation Mistakes
| # | Scenario | Status | Safeguard |
| --- | --- | --- | --- |
| 16 | Keyword vs ASIN confusion. | implemented | ASIN-like customer search terms receive product-targeting risk labels. |
| 17 | Auto campaign targeting confusion. | implemented | Auto targeting values like substitutes, close match, loose match, complements are flagged. |
| 18 | Match type missing or shown as `-`. | implemented | Missing/`-` match type is flagged as auto/product-targeting uncertainty. |
| 19 | Same search term performs differently by product. | implemented | Duplicate analysis checks product-specific keys. |
| 20 | Same search term performs differently by match type. | implemented | Duplicate analysis checks match-type-specific keys. |

## 4. Campaign Creation Mistakes
| # | Scenario | Status | Safeguard |
| --- | --- | --- | --- |
| 21 | Wrong Hero keyword selected by one metric only. | in_progress | Hero selection uses relevance and search volume; safety summary flags ASIN-like, duplicate, and low-data terms. Performance reliability inputs remain pending. |
| 22 | Creating campaigns from low-data keywords. | in_progress | Monitoring/risk validator reject or warn on low sample size; campaign generation still needs an explicit keyword-set threshold gate. |
| 23 | Creating campaigns from irrelevant accidental-sale terms. | in_progress | Relevance and review stages exist; explicit accidental-sale guard remains pending. |
| 24 | Bad grouping of unrelated, branded, competitor, generic, high/low-intent, or variant terms. | in_progress | Campaign structure analysis flags mixed intent; campaign plan grouping still needs stronger grouping constraints. |
| 25 | Naming convention mistakes. | implemented | Campaign names follow documented product/SP/manual/match/group/date format. |
| 26 | Duplicate campaign creation. | in_progress | Campaign plan now marks existing-campaign duplicate check as required; live inventory comparison remains pending. |
| 27 | Wrong budget applied and total daily exposure hidden. | implemented | Campaign plan safety summary shows aggregate daily budget exposure and requires budget confirmation. |
| 28 | Wrong bid applied; blind suggested bids and compounding increases. | in_progress | Monitoring bid changes are capped and approval-controlled; campaign creation still needs margin-aware suggested-bid guard. |

## 5. Negative Keyword Mistakes
| # | Scenario | Status | Safeguard |
| --- | --- | --- | --- |
| 29 | Negative exact added incorrectly. | implemented | Negative exact recommendations are explicit, approval-controlled, and trace to rules. |
| 30 | Negative phrase added too aggressively. | in_progress | Phrase negatives require higher thresholds; additional broad-blocking explanation is needed in UI. |
| 31 | Blocking best terms at wrong campaign/ad group level. | in_progress | Safeguards reject negatives on converting terms; UI/export should show placement level clearly. |
| 32 | Adding negatives before enough data. | implemented | Negative recommendations require click thresholds and no orders. |
| 33 | Not separating harvesting and ranking campaigns. | in_progress | Campaign structure analysis flags overlap; stronger exact/phrase/broad separation checks remain pending. |

## 6. Monitoring And Optimization Mistakes
| # | Scenario | Status | Safeguard |
| --- | --- | --- | --- |
| 34 | Increasing bids just because budget is not fully spent. | implemented | Rules avoid budget-only bid increases and require performance signals. |
| 35 | Ignoring profit margin and break-even ACOS. | in_progress | Product target ACOS is used; explicit margin/break-even ACOS collection remains pending. |
| 36 | Judging too early despite attribution delay. | in_progress | Monitoring windows are documented; safeguards flag 7-day/14-day attribution window context. |
| 37 | Ignoring attribution window differences. | implemented | Safeguards detect 7-day vs 14-day metric headers. |
| 38 | Not checking spend/click/order thresholds. | implemented | Monitoring and risk validator use thresholds and evidence strength. |
| 39 | Ignoring clicks/spend with no sales. | implemented | Zero-sales spend risk labels and no numeric ACOS when sales are zero. |
| 40 | Ignoring high spend, low order terms. | implemented | High ACOS/high spend low sales rules create review recommendations. |
| 41 | Ignoring low impression issue causes. | in_progress | Low-impression signals exist; root-cause checklist is documented but not fully modeled. |
| 42 | Ignoring Buy Box/listing health. | todo | Needs listing-health inputs before rules can distinguish keyword vs listing issues. |

## 7. Analyst Confusion Scenarios
| Audience | Confusion | Status | Safeguard |
| --- | --- | --- | --- |
| Junior | ACOS vs ROAS. | implemented | Metrics glossary and deterministic fields clarify lower ACOS/higher ROAS. |
| Junior | Sales vs profit. | in_progress | Margin risk label exists; full profit model pending. |
| Junior | Clicks vs conversions. | implemented | CTR/CVR/order evidence shown separately. |
| Junior | CTR vs conversion rate. | implemented | Deterministic metric fields separate both. |
| Junior | Orders vs units. | implemented | Unit/order mismatch warning. |
| Junior | Search term vs targeting. | implemented | Both are separate entity fields in snapshots and evidence. |
| Junior | Keyword vs ASIN. | implemented | ASIN-like term risk label. |
| Junior | Blank ACOS. | implemented | Blank ACOS is no-sales/no-spend, never good performance. |
| Junior | Campaign-level vs search-term-level data. | implemented | Evidence includes report/campaign/ad group/target/search-term rollups. |
| Junior | Too little data. | implemented | Evidence-strength and threshold gates. |
| Senior | Attribution delay. | in_progress | Window warnings added; delayed-attribution model pending. |
| Senior | Aggregated data hiding problems. | implemented | Rollups and duplicate overlap included. |
| Senior | Branded vs non-branded mixing. | in_progress | Structure analyzer supports brand terms; product brand inputs pending. |
| Senior | Other SKU sales. | implemented | Other-SKU dominance warning. |
| Senior | Cannibalization. | todo | Requires organic/conversion baseline inputs. |
| Senior | Seasonality. | todo | Requires historical/seasonal context inputs. |
| Senior | Budget illusion. | in_progress | Rules avoid budget-only increases; root-cause explanations pending. |
| Senior | Wrong break-even ACOS. | in_progress | Target ACOS exists; margin-backed break-even pending. |
| Senior | Portfolio-level confusion. | in_progress | Workspace/product scoping exists; portfolio-level analysis pending. |
| Senior | Over-automation trust. | implemented | Human approval and audit boundaries remain mandatory. |

## 8. Ways Amazon Ads Optimization Wastes Money
| # | Danger zone | Status | Safeguard |
| --- | --- | --- | --- |
| 1 | Increasing bids on low-converting keywords. | implemented | Bid increases require stronger conversion/low-impression signals and review. |
| 2 | Scaling keywords with only 1 sale. | in_progress | Hero/move-to-exact rules require more orders; campaign plan threshold pending. |
| 3 | Not adding negatives to wasteful search terms. | implemented | Zero-order click/spend negative review rules. |
| 4 | Adding negatives too aggressively and blocking good terms. | implemented | No negatives on converting terms; threshold and approval gates. |
| 5 | Creating duplicate campaigns for same terms. | todo | Existing campaign inventory check pending. |
| 6 | Mixing branded, competitor, generic terms. | in_progress | Structure analyzer supports separation; inputs pending. |
| 7 | Using 50% ACOS when margin is lower. | in_progress | Target ACOS configurable on product; margin model pending. |
| 8 | Ignoring zero-sales spend. | implemented | Zero-sales spend risk label. |
| 9 | Using broad match without strict monitoring. | implemented | Broad/auto risk signals and negative phrase review threshold. |
| 10 | Moving irrelevant search terms into Exact campaigns. | in_progress | Move-to-exact requires orders and ACOS; relevance guard pending. |
| 11 | Not separating keyword campaigns from product targeting campaigns. | implemented | ASIN-like terms and product targeting contexts are flagged. |
| 12 | Not checking total daily budget before campaign creation. | implemented | Campaign plan safety summary shows aggregate daily budget exposure and requires budget confirmation. |
| 13 | Using Amazon suggested bids blindly. | in_progress | Bid caps exist for monitoring; campaign creation margin guard pending. |
| 14 | Optimizing before enough data is collected. | implemented | Evidence thresholds and low-data watch locks. |
| 15 | Not checking advertised SKU vs other SKU sales. | implemented | Other-SKU dominance warning. |
| 16 | Treating ASINs as keywords. | implemented | ASIN-like term risk label. |
| 17 | Not checking campaign overlap. | implemented | Duplicate/overlap signals in rollups and safeguards. |
| 18 | Not checking listing conversion problems. | todo | Requires listing-health data. |
| 19 | Optimizing based only on ACOS. | implemented | Evidence includes CTR, CPC, CVR, ROAS, CPA, spend/order, shares, and risk labels. |
| 20 | Ignoring profit, refund rate, COGS, and fees. | todo | Requires financial inputs beyond current MVP data. |

## 9. Required Safeguards
| Safeguard | Status | Implementation notes |
| --- | --- | --- |
| Correct report type. | implemented | Deterministic report detection. |
| Required columns exist. | implemented | Detector and monitoring normalization enforce required headers. |
| Date range valid. | implemented | Date serial conversion implemented; row-level invalid date ranges and import-level mixed date ranges are flagged. |
| Currency consistent. | implemented | Safeguard warning. |
| Marketplace consistent. | implemented | Safeguard warning. |
| No completely empty rows. | implemented | Parser skips empty spreadsheet rows and stores CSV empty cells as null. |
| Numeric columns numeric. | implemented | Monitoring normalization rejects invalid/negative numeric values. |
| Percentage columns handled correctly. | implemented | Percent parser supports percent strings and decimals. |
| Sales/spend/clicks/orders not negative. | implemented | Monitoring normalization rejects negatives; safeguards warn. |
| Recalculate CTR/CPC/ACOS/ROAS/CVR and compare with Amazon values. | implemented | Safeguards emit metric mismatch warnings. |
| Minimum data rules. | implemented | Monitoring/risk validator thresholds and evidence strength. |
| Human review checkpoints. | in_progress | Approval boundary exists; data-quality warnings explicitly separate ASIN/product-targeting rows from keyword rows before optimization; UI-specific checkpoints remain pending. |
| Risk labels: safe, needs review, high risk, not enough data, duplicate, ASIN targeting, branded, irrelevant, zero-sales spend, margin risk. | in_progress | Core deterministic labels implemented; branded/irrelevant require product/account term inputs. |

## 10. Most Important Rule
Status: documented and in_progress.

The system must ask: is this search term relevant, statistically reliable, profitable after margin, correctly classified, and safe to scale? ACOS alone is never enough.
