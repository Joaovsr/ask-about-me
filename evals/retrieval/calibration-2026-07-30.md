# Retrieval calibration and holdout — 2026-07-30

The weighted lexical candidate was staged with 11 published sources and kept inactive
during this evaluation.

- Candidate generation: `db2cfd8f-aa89-47b5-92a7-2baf25455777`
- Previous active generation: `c9f36f5e-b2d1-4706-89a3-fb561398ff3e`
- Retrieval: `hybrid-rrf-v2`
- Query strategy: `deterministic-query-v2`
- Embedding: `openai/text-embedding-3-small/1536`
- Chunker: `section-token-v1:text-embedding-3-small:350:500:50`
- Lexical strategy: `weighted-portuguese-v1`
- Support rule: `support-v2`
- Raw thresholds: cosine similarity `0.45` or `ts_rank_cd` `0.05`

`support-v2` also accepts a strict published-title match and rejects explicit generic
implementation/tutorial requests after retrieval. This negative signal was necessary
because “Ensine como criar uma medida DAX no Power BI” had cosine similarity `0.557`,
while valid cross-language questions required a lower semantic threshold. RRF was not
used as a support threshold.

## Calibration split

| Metric | Result |
| --- | ---: |
| Cases | 12 |
| Hybrid Recall@5 | 0.8889 |
| Hybrid Recall@8 | 0.9444 |
| Hybrid MRR | 1.0000 |
| Hybrid nDCG@5 | 0.9247 |
| Supported precision | 1.0000 |
| Supported recall | 1.0000 |
| False acceptances / rejections | 0 / 0 |

The calibration ranking gate did not pass. `pt-audit-power-bi` retrieved
`fictor360_pbi` in the top 5 but not the secondary `atalaia` qrel because several chunks
from the strongest sources occupied those positions. This remains a source-coverage
signal for a future ranking/diversity experiment; it did not require weakening the
support gate.

## Holdout split

| Metric | Result |
| --- | ---: |
| Cases | 12 |
| Hybrid Recall@5 | 1.0000 |
| Hybrid Recall@8 | 1.0000 |
| Hybrid MRR | 0.8333 |
| Hybrid nDCG@5 | 0.8829 |
| Supported precision | 1.0000 |
| Supported recall | 1.0000 |
| False acceptances / rejections | 0 / 0 |
| Critical failures | 0 |
| Activation gate | passed |

The evaluator made no generation calls. The candidate was intentionally not activated
as part of this validation, so rollback remained the previously active generation.
