# Detector calibration protocol

No licensed evaluation corpus or approved calibrated model is supplied. Production
inference remains unavailable/experimental; test fixtures are arithmetic and contract
tests only. They are never production calibration evidence.

Run inside the verification container with `PYTHONPATH=/app`:

```
python scripts/detector_calibration.py --input /datasets/frozen-scores.json --output /results/evaluation.json
```

The input contains `provenance` (source, collection_method, license, curator,
created_at), dataset_version, model_revision, pipeline_version, runtime, hardware,
purpose, `dataset` metadata rows and `predictions`. Dataset rows follow the existing
`DatasetRow` contract: unique example_key, split, label, text_sha256, author_key_hash,
document_key_hash, optional source_document_hash and stratification metadata.
Prediction rows reference exactly each non-training example, preserving its split and
label, and contain a finite model score. No raw customer document is required.

All five train/validation/calibration/test/ood splits must exist. Duplicate text,
author/source-document leakage, unmatched scores and missing provenance fail closed.
Known-origin labels distinguish HUMAN, AI_GENERATED, AI_ASSISTED, HUMAN_EDITED_AI and
MIXED. Unknown-ground-truth OOD examples belong only to the OOD split. Transformations
such as translation/paraphrase belong in metadata with their known origin retained.

A deterministic monotonic logistic calibrator fits only the calibration split.
Operating thresholds use only human validation scores. Those parameters are frozen
before test/OOD evaluation. Reports include AUROC, average-precision AUPRC, precision,
recall, F1, Brier score, ECE, binary confusion matrix, coverage and TPR/observed FPR at
validation thresholds targeting 0.1%, 1% and 5% FPR. The binary target is any AI
involvement; it does not establish wholly machine-written authorship. Ties are handled
as groups. Target FPR is not a guarantee on unseen test data, and empirical sample
resolution is not a confidence bound.

The existing evaluation module supplies language/domain/genre/length/proficiency/
generator/editing breakdowns. A real release dataset must additionally document
unseen-generator and domain-shift separation, short/long inputs, licensed non-native
English and each claimed language. Missing strata, insufficient human examples and
incomplete mixed/assisted/edited classes remain review blockers. Error, subgroup and
robustness review and independent promotion are required; this CLI never grants
production approval.

Public results add `authorship_assessment`: LIKELY_HUMAN, LIKELY_MACHINE,
MIXED_OR_EDITED or INDETERMINATE. Experimental, unvalidated and abstained results
expose no authorship confidence/probability. Historical internal verdict names remain
for compatibility. Minimum-length abstention in the existing pipeline is preserved.
