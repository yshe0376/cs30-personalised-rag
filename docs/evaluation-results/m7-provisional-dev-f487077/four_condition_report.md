# Four-condition evaluation report

Report status: **DEVELOPMENT / NOT FOR FORMAL CLAIMS**

Source run: `member7-four-condition-861e54acc967c869`

Cases: 36; rows: 144

Every row was joined to its immutable source case and accepted only after the reconstructed prompt SHA-256 matched M7's saved generation trace.

## Four-condition comparison

| Split | Level | Metric | Plain | Prompt only | Reranking only | Combined |
|---|---|---|---:|---:|---:|---:|
| dev | advanced | answer_choice_accuracy_all | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| dev | advanced | answer_choice_accuracy_answered | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| dev | advanced | abstention_accuracy | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| dev | advanced | citation_validity | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| dev | advanced | gold_evidence_citation_coverage | 0.8333 | 0.8333 | 0.8333 | 0.8333 |
| dev | advanced | repair_rate | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| dev | advanced | technical_failure_rate | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| dev | advanced | provider_failure_rate | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| dev | beginner | answer_choice_accuracy_all | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| dev | beginner | answer_choice_accuracy_answered | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| dev | beginner | abstention_accuracy | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| dev | beginner | citation_validity | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| dev | beginner | gold_evidence_citation_coverage | 0.8333 | 0.8333 | 0.8333 | 0.8333 |
| dev | beginner | repair_rate | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| dev | beginner | technical_failure_rate | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| dev | beginner | provider_failure_rate | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| dev | intermediate | answer_choice_accuracy_all | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| dev | intermediate | answer_choice_accuracy_answered | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| dev | intermediate | abstention_accuracy | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| dev | intermediate | citation_validity | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| dev | intermediate | gold_evidence_citation_coverage | 0.8333 | 0.8333 | 0.8333 | 0.8333 |
| dev | intermediate | repair_rate | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| dev | intermediate | technical_failure_rate | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| dev | intermediate | provider_failure_rate | 0.0000 | 0.0000 | 0.0000 | 0.0000 |

Rates use explicit per-scope denominators. Technical failures are not treated as abstentions, and provider failures remain separately visible.
