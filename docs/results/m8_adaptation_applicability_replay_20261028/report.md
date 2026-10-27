# Offline adaptation applicability replay

No API calls or retry calls.

- high: 6/30 requests rejected; 80 always-assessed verdicts checked; violations {'B4': 6}.
- low: 5/30 requests rejected; 80 always-assessed verdicts checked; violations {'B4': 5}.

Rejected outputs would enter the existing live retry path. No verdict is changed here; the saved trial remains historical evidence.
