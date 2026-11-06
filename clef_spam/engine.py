from dataclasses import asdict
from time import monotonic
from .backends import build
from .contracts import ClassificationRequest, Classification, ScoreKind
from .errors import BackendError, ConfigError, InvalidResponse, BackendsExhausted
from .message import prepare


def decide(result, policy, truncated):
    if truncated and not policy.allow_truncated_input:
        return "uncertain", "truncated_input"
    if result.score_kind == ScoreKind.REPORTED_SCORE and not policy.allow_reported_scores:
        return "uncertain", "reported_score_requires_opt_in"
    if result.spam_score >= policy.spam_threshold:
        return "spam", "spam_threshold"
    if result.spam_score <= policy.ham_threshold:
        return "ham", "ham_threshold"
    return "uncertain", "between_thresholds"

class Classifier:
    """Reusable, serial classifier. Only retryable failures trigger fallback."""
    def __init__(self, config):
        self.config = config
        self.backends = {}
        try:
            for name in config.backend_order:
                self.backends[name] = build(config.backends[name])
        except Exception:
            self.close()
            raise

    def close(self):
        for backend in self.backends.values():
            backend.close()
        self.backends.clear()

    def classify(self, raw):
        if not self.backends:
            raise ConfigError("no enabled backend selected; edit config.json first")
        msg = prepare(raw, self.config.max_message_bytes, self.config.max_text_chars)
        failures = []
        started = monotonic()
        for name, backend in self.backends.items():
            try:
                result = backend.classify(ClassificationRequest(msg.state, self.config.question))
                if not isinstance(result, Classification):
                    raise InvalidResponse("backend violated Classification return contract")
                if result.score_kind != backend.capabilities.score_kind:
                    raise InvalidResponse("backend returned score semantics inconsistent with capabilities")
            except BackendError as exc:
                failures.append({"backend": name, "code": exc.code, "retryable": exc.retryable})
                if not exc.retryable:
                    raise
                continue
            except Exception:
                raise BackendError("backend plugin raised an unexpected exception") from None
            truncated = msg.truncated or result.input_truncated
            verdict, reason = decide(result, self.config.policy, truncated)
            action = "observe" if self.config.policy.observe_only else ("junk" if verdict == "spam" else "deliver")
            return {"schema_version": 1, "message_sha256": msg.digest, "backend": name,
                    "classification": asdict(result), "input_truncated": truncated,
                    "verdict": verdict, "reason": reason, "action": action,
                    "observe_only": self.config.policy.observe_only,
                    "elapsed_ms": round((monotonic() - started) * 1000, 2), "fallback_errors": failures}
        # No fabricated score or delivery decision on inference failure.
        raise BackendsExhausted(failures)
