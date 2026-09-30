"""Independent source-support review, separate from rewrite equivalence."""

import json

from app.modules.inference.gateway import AzaeronInferenceJob
from app.modules.inference.registry import InferenceUnavailable
from app.modules.verification.service import SemanticAssessment


async def assess_support(private, result, identity, source, *, mode="grounded_support"):
    verifier = private.router.route("verify")
    if (
        verifier.model_id == result.model_id
        or verifier.revision == result.model_revision
    ):
        raise InferenceUnavailable("independent_verifier_required")
    review = await private.run(
        AzaeronInferenceJob(
            **identity,
            task="verify",
            text=json.dumps(
                {
                    "mode": mode,
                    "original": source,
                    "candidate": result.output,
                    "policy": "Assess whether all candidate factual claims are supported by supplied evidence. Omissions are allowed in summaries. If evidence is insufficient return uncertain. No outside sources are available.",
                },
                ensure_ascii=False,
            ),
            max_output_tokens=256
        )
    )
    try:
        assessment = SemanticAssessment.model_validate_json(review.output)
    except ValueError:
        raise InferenceUnavailable("verifier_invalid_output") from None
    passed = assessment.equivalent and not (
        assessment.contradiction
        or assessment.unsupported_additions
        or assessment.uncertain
    )
    return {
        "outcome": "VERIFIED" if passed else "REJECTED",
        "model_id": review.model_id,
        "model_revision": review.model_revision,
        **assessment.model_dump(),
    }
