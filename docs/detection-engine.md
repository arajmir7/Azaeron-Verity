# AZAERON VERITY detection engine

The detection engine is an evidence-producing inference pipeline, not a
single AI percentage:

`DOCUMENT → SEGMENT → FEATURES → MODEL ENSEMBLE → CALIBRATION → UNCERTAINTY → EVIDENCE`

## Serving contract

Every signal provider implements `SignalProvider.extract(...)` and returns a
`ProviderOutput` containing:

- provider and implementation version;
- signal family and status;
- descriptive features;
- optional normalized `score` and `confidence`;
- model version;
- provider-contextualized evidence records.

Deterministic feature providers intentionally return `score=None` and
`confidence=None` because their measurements are not validated AI-use
probabilities. Their measured values remain in the evidence records. An
invalid provider output, provider exception, classifier exception, or
uncalibrated model is withheld and recorded as an abstention event.

The default providers are:

| Family | Default state | Production meaning |
| --- | --- | --- |
| linguistic | OBSERVED | Descriptive lexical measurements only |
| stylometric | OBSERVED | Descriptive style measurements only |
| syntactic | OBSERVED | Conservative rule-derived measurements |
| document | OBSERVED | Document and segmentation metadata |
| segment | OBSERVED | Segment-level descriptive measurements |
| semantic | UNAVAILABLE | Requires a validated semantic model |
| authorship | UNAVAILABLE | Requires a validated baseline; never identity attribution |
| revision/provenance | OBSERVED or UNAVAILABLE | Depends on supplied lineage metadata |

## Model and calibration gate

`CalibrationLayer` is the runtime registry for loaded classifier/calibrator
pairs. Registration requires a held-out evaluation dataset and a calibration
version. A `PRODUCTION` registration additionally requires an explicit passing
validation-gate record (`promotion_allowed=true`). Model probabilities must
contain all six states and sum to one before calibration.

The persisted `ModelRegistry` is governed by the evaluation gate in
`app.modules.governance`. Its lifecycle is:

`EXPERIMENTAL → CANDIDATE → PRODUCTION → RETIRED`

The default production-shaped deployment has no validated classifier loaded.
It therefore extracts real descriptive signals and abstains with
`INSUFFICIENT_EVIDENCE`. It does not expose fabricated probabilities or claim
AI use.

## Runtime decision policy

The ensemble preserves each provider’s evidence and model metadata. It
abstains when:

- no calibrated classifier is available;
- a provider or classifier fails;
- ensemble uncertainty is high;
- maximum calibrated confidence is below the serving threshold;
- the winning state is `UNCERTAIN` or `INSUFFICIENT_EVIDENCE`.

`PRODUCTION` appears on an inference only when every participating calibrated
model is registered as `PRODUCTION` through the validated held-out gate.
