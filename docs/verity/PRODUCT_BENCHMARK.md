# Product benchmark: academic writing and evidence workflows

Reviewed 2026-09-28. This is a bounded review of the products shown in the
reference screenshots, their official product pages, Turnitin's own guidance,
and primary research on detector limitations. Vendor performance and coverage
claims below are **claims**, not independently verified Azaeron results.

| User job | Observed market pattern | Azaeron response |
| --- | --- | --- |
| Start from a draft | [Phrasly](https://phrasly.ai/ai-detector), [HumanizeAI.pro](https://www.humanizeai.pro/detector), and [StealthWriter](https://stealthwriter.ai/ai-detector) put a text box or paste action first. | Check now accepts pasted or typed text as well as a file. Both create the same private, fingerprinted, immutable document version. |
| Improve writing | [StealthWriter](https://stealthwriter.ai/) advertises rewrite intensity and sentence alternatives; [Phrasly](https://phrasly.ai/ultra) advertises modes and meaning preservation. | Offer honest editorial focus controls for grammar/spacing, clarity/brevity, or academic tone. Keep each suggestion's original text, revision, reason, protected spans, and version history. Generative rewriting is gated until a licensed private model and independent verifier are evaluated. |
| Interpret AI-writing signals | Several vendors show prominent percentages or sentence scores. [Turnitin's guide](https://guides.turnitin.com/hc/en-us/articles/22774058814093-Using-the-AI-Writing-Report) says its model can misidentify human, AI, and paraphrased text, and should not be the sole basis for adverse action. | Continue to abstain when calibration or evidence is insufficient. Never display a fabricated probability, imply equivalence with Turnitin, or treat a signal as proof of misconduct. |
| Review source overlap | [Phrasly](https://phrasly.ai/) includes a plagiarism checker in its hub. [Turnitin](https://guides.turnitin.com/hc/en-us/articles/23713493434253-Understanding-the-similarity-score-for-students) explains that a high similarity score does not always mean plagiarism and a low score does not rule it out. | Show exact matched passages, source versions, citation/quotation context, exclusions, and corpus coverage. Name the result “similarity review,” not a plagiarism verdict or a web-wide scan. |
| Defend a research or teaching decision | [UNESCO's guidance](https://www.unesco.org/en/articles/guidance-generative-ai-education-and-research?hub=83294) centers human agency in education and research. A [primary study of detector bias](https://doi.org/10.1016/j.patter.2023.100779) found substantial misclassification of writing by non-native English speakers in the detectors studied; those results cannot be generalized to every current detector. | Make document version, sources, limitations, and review actions available to writers and reviewers. Evaluate any future detector across relevant language and writing groups before release. |

## Product decisions

1. **One document, connected workflows.** A student can start with a draft;
   a researcher can inspect a claim and source; an educator can review evidence
   and history. These actions should retain document and version context.
2. **Quality is measured by fidelity.** Future writing-model evaluation must
   measure factual preservation, citation and quotation integrity, protected
   spans, clarity, user acceptance, and latency. A detector “pass rate” is not
   a writing-quality or academic-integrity metric.
3. **No invented certainty.** Detector probabilities require calibration and
   fairness evidence. Similarity requires a stated comparison corpus. A missing
   source, model, or verification step remains visibly unavailable.
4. **No tool sprawl.** The current research, citation, similarity, provenance,
   report, and editor views already address the core jobs. Prioritize shorter
   paths between them over chatbot, flashcard, image, or transcript features
   without a validated use case and operating model.

The current release remains **not production ready**. See
[release certification](RELEASE_CERTIFICATION.md) for executed tests and blockers.
