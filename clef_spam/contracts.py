"""Public plugin contracts. Backends classify; they never decide delivery."""
from dataclasses import dataclass
from enum import StrEnum
import math
from typing import Protocol, runtime_checkable

from .errors import InvalidResponse

class ScoreKind(StrEnum):
    NATIVE_PROBABILITY = "native_probability"
    REPORTED_SCORE = "reported_score"

@dataclass(frozen=True)
class ClassificationRequest:
    state: str
    question: str

@dataclass(frozen=True)
class BackendCapabilities:
    score_kind: ScoreKind
    local: bool = False
    # HTTP backends enforce I/O timeouts. Local GPU execution is not preemptible.
    hard_timeout: bool = False

@dataclass(frozen=True)
class Classification:
    spam_score: float
    score_kind: ScoreKind
    model: str
    input_truncated: bool = False

    def __post_init__(self):
        if (isinstance(self.spam_score, bool) or
                not isinstance(self.spam_score, (float, int)) or
                not math.isfinite(self.spam_score) or not 0 <= self.spam_score <= 1):
            raise InvalidResponse("spam score must be a finite number between 0 and 1")
        if not isinstance(self.score_kind, ScoreKind):
            raise InvalidResponse("unknown score semantics")
        if not isinstance(self.model, str) or not self.model.strip():
            raise InvalidResponse("response model must be a nonempty string")
        if type(self.input_truncated) is not bool:
            raise InvalidResponse("input_truncated must be boolean")

@runtime_checkable
class Backend(Protocol):
    """Factories receive an options dict and return a reusable Backend.

    classify must return Classification or raise BackendError. Never log mail,
    credentials, or provider response bodies. Instances are used serially;
    callers must provide synchronization before sharing across threads.
    close must be safe after a failed classify and must not raise.
    """
    capabilities: BackendCapabilities
    def classify(self, request: ClassificationRequest) -> Classification: ...
    def close(self) -> None: ...
