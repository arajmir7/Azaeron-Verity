"""Small specialist output contracts shared by gateway and native runtime."""

from typing import Literal
from pydantic import Field, model_validator
from .policy import Digest, StrictModel


class DetectionOutput(StrictModel):
    label: Literal["HUMAN", "AI", "MIXED", "UNCERTAIN"]
    probabilities: list[float] | None = Field(min_length=3, max_length=3)
    abstained: bool
    checkpoint_sha256: Digest
    calibration_sha256: Digest
    limitations: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def calibrated(self):
        import math

        if self.abstained:
            if self.label != "UNCERTAIN" or self.probabilities is not None:
                raise ValueError("Abstention must withhold probabilities")
            return self
        if self.label == "UNCERTAIN" or self.probabilities is None:
            raise ValueError("Accepted labels require calibrated probabilities")
        if (
            any(not math.isfinite(p) or not 0 <= p <= 1 for p in self.probabilities)
            or abs(sum(self.probabilities) - 1) > 1e-5
        ):
            raise ValueError("Invalid class probabilities")
        if (
            self.label
            != ["HUMAN", "AI", "MIXED"][
                max(range(3), key=self.probabilities.__getitem__)
            ]
        ):
            raise ValueError("Label does not match calibrated probabilities")
        return self
