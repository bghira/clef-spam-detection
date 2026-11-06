# Backend contracts


Public types are in `clef_spam.contracts`:

```python
from clef_spam.contracts import (
    BackendCapabilities, Classification, ClassificationRequest, ScoreKind,
)

class MyBackend:
    capabilities = BackendCapabilities(ScoreKind.NATIVE_PROBABILITY)

    def __init__(self, options: dict):
        # Validate known options; don't perform inference/downloads here.
        pass

    def classify(self, request: ClassificationRequest) -> Classification:
        # Provider-specific request and strict response validation goes here.
        # Return the probability that request.question is YES.
        return Classification(0.5, ScoreKind.NATIVE_PROBABILITY, "my-model")

    def close(self) -> None:
        # Idempotent; safe following a failed classify; never raise.
        pass
```

A backend factory receives a fresh options dict and returns an object implementing
`Backend`. Register an installed package entry point:

```toml
[project.entry-points."clef_spam.backends"]
my_backend = "my_package.backend:MyBackend"
```

Use `"type": "my_backend"` in config. Built-in names are reserved; duplicate
plugin names are rejected. Only selected plugins are loaded, so optional backend
dependencies do not affect other adapters. Plugins are trusted executable code.
Return immutable `Classification` values with finite scores in [0,1] and exactly
the declared score semantics. Never return provider payloads or secrets as errors.

Raise errors from `clef_spam.errors`:

| Error | Retryable / fallback |
| --- | --- |
| `AuthenticationError` | No |
| `InvalidResponse` | No |
| `UnsupportedCapability` | No |
| `RateLimitError` | Yes |
| `BackendTimeout` | Yes |
| `BackendUnavailable` | Yes |

Do not swallow these as ham. Unexpected plugin exceptions and invalid return
values stop classification. `Classifier.close()` releases every initialized
backend. A Classifier is a serial API; services must bound concurrency and avoid
sharing it unsynchronized. Backend capability flags describe local execution and
hard timeout support; no bundled backend currently claims a hard total deadline.
The engine has no shared cache, circuit breaker, persistent queue, or per-recipient
policy. Delivery queue ownership belongs to the mail-server adapter.

