# Model validation gate

A model may be registered as `EXPERIMENTAL` or `CANDIDATE` while evaluation is
in progress. `PRODUCTION` requires a frozen immutable dataset version and a
report produced by `evaluate_predictions` with:

- exact-text, author, document, source-document, and split contamination checks;
- held-out test metrics: precision, recall, F1, FPR, FNR, AUROC, and AUPRC;
- calibration error and confidence reliability;
- breakdowns for language, domain, genre, document length, writing proficiency,
  generation source, and editing intensity;
- false-positive, false-negative, confidence-failure, distribution-shift, and
  OOD error analysis;
- complete reproducibility metadata: seed, code, feature, pipeline, manifest,
  and inference-configuration identities;
- documented limitations and a controlled false-positive rate.

Dataset provenance is part of the manifest hash. Once frozen, PostgreSQL
triggers reject updates, deletes, and example mutations. A failed gate raises
an exception for production promotion; no score is promoted by default.

