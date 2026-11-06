# clef-spam-detection

Email classification using Cloudflare Clef, with explicit probability semantics,
replaceable inference backends, and a delivery-policy layer. Python 3.11+.
The core and HTTP backends have **no third-party runtime dependencies**.

This first version classifies messages and provides a byte-stream filter plus a
Sieve example. It does **not** run an SMTP/LMTP listener, deliver messages, install
mail-server configuration, or generate learned rules.

## Start locally

```sh
python3 -m venv .venv
.venv/bin/pip install -e .
cp config.json.example config.json
.venv/bin/clef-spam --config config.json validate
```

Every example backend is disabled. Validation reports `ready: false` until you:

1. Set one backend's `disabled` to `false` and fill its options.
2. Add its configuration name to `backend_order` (for example `["cloudflare"]`).
3. Export the environment variable named by `api_key_env` for authenticated APIs.

All enabled backends must appear exactly once in the order. An omitted `disabled`
means disabled. `config.json` is ignored by Git. Store credentials in environment
variables rather than config; config may still contain private infrastructure
addresses. Run from this directory or pass an absolute `--config` path.

```sh
.venv/bin/clef-spam --config config.json classify message.eml
# Or read RFC 5322 bytes from stdin:
.venv/bin/clef-spam --config config.json classify < message.eml
# Write a filtered message to a NEW file (never overwrite the input):
.venv/bin/clef-spam --config config.json filter message.eml > filtered.eml
```

`classify` emits JSON. `filter` emits email bytes with regenerated `X-Clef-*`
headers. Neither sends or moves mail. Errors go to stderr as JSON, without
fabricating a ham result. Exit status: 0 success, 2 configuration error, 1 input,
backend, or I/O failure. A caller must check the exit status before accepting the
output; shell redirection may leave an empty output file after failure.

## Questions, scores, and delivery policy

`question` is configurable, but **yes must mean spam**. For example:
`Is this unsolicited spam or a phishing email?` Inverting the question without
changing the interpretation would invert your policy.

Workers AI, SystemOne, and Transformers use Clef's native `noul` answer: the
probability of yes. They never mistake a choice's certainty for spam probability.
The chat adapter requests strict JSON with `spam_score`; this is a model-reported
score, not a calibrated Clef probability. `score_kind` preserves that distinction.
Native probabilities also need evaluation on your own spam and ham: a threshold
of 0.98 does not promise a 2% false-positive rate.

Policy defaults:

- `spam_threshold: 0.98`: scores at or above this are spam.
- `ham_threshold: 0.1`: scores at or below this are ham; values between abstain.
- `observe_only: true`: every successful classification has `action: observe`.
- `allow_reported_scores: false`: chat results abstain unless explicitly allowed.
- `allow_truncated_input: false`: known-truncated evidence abstains.

With observation disabled, spam yields `action: junk`; ham and uncertain yield
`action: deliver`. These are recommendations, not mail delivery operations.
`reason` explains abstention. No backend or unsuccessful inference is an error,
not an ordinary uncertain/ham classification. There is currently one global
policy per config, not recipient-specific policy.

Example output (timing and digest abbreviated):

```json
{
  "schema_version": 1,
  "message_sha256": "...",
  "backend": "cloudflare",
  "classification": {
    "spam_score": 0.99,
    "score_kind": "native_probability",
    "model": "clef",
    "input_truncated": false
  },
  "input_truncated": false,
  "verdict": "spam",
  "reason": "spam_threshold",
  "action": "observe",
  "observe_only": true,
  "elapsed_ms": 100.0,
  "fallback_errors": []
}
```

## Built-in backends

| Type | Endpoint / inference | Score semantics |
| --- | --- | --- |
| `workers_ai` | Cloudflare account REST `/ai/run/@cf/cloudflare/clef` or `clef-flash` | Native probability |
| `systemone` | Full configured URL, e.g. `http://127.0.0.1:30000/v1/systemone` | Native probability |
| `openai_compatible` | Full chat-completions URL; JSON mode required | Reported score |
| `transformers` | Local Clef backbone **and joint schema head** | Native probability |

The SystemOne adapter accepts the direct `answers` response; Workers AI unwraps
the Cloudflare `success`/`result` envelope. Chat endpoints must support
`response_format: {"type":"json_object"}`, `temperature`, and the documented
response shape, including `finish_reason: "stop"`; unsupported servers fail
explicitly. An OpenAI-compatible chat endpoint is not a native Clef endpoint.

HTTP uses system TLS verification, rejects redirects, caps response size at 1 MiB,
and permits plaintext only on loopback. `timeout_seconds` is a socket I/O timeout,
**not a hard total deadline** for a server that slowly streams bytes. Add a
supervisor deadline when integrating into mail delivery. No built-in automatic
retries or backoff: only retryable failures advance to the next selected backend.
Authentication, schema, and contract errors stop immediately. Rate limits,
connection failures, timeouts, and HTTP 5xx responses permit fallback. Fallback
only occurs for errors, not for uncertain or non-actionable classifications.

### Local Transformers

```sh
.venv/bin/pip install -e '.[transformers]'
```

Then enable `local_clef`, set a model's immutable 40-character revision SHA, and
set `trust_remote_code: true` only after reviewing that revision's
`joint_schema_model.py`. The model's official loader executes that code. The
adapter lazily downloads that pinned revision, loads both backbone and decision
head once per `Classifier`, uses inference mode, and serializes local calls.
It does **not** use `pipeline("text-generation")`. Keep a Classifier alive for
repeated local inference; the CLI is one process per message and would otherwise
reload the model each time. GPU memory and optional library compatibility are
operator concerns; there is no quantization or CPU-offload layer here.

Local inference has no preemptive deadline. Truncation is checked against the
encoder's token budget. Remote truncation is recognized only if the provider
reports it; the default 16,000-character preprocessing bound is independent of
the model's token context limit. Local weights were not downloaded or GPU-tested
as part of development; HTTP adapters are tested against local fixture servers,
not production provider accounts.

## Email handling and privacy

The parser reads at most `max_message_bytes + 1` bytes and rejects oversized
messages; it never silently cuts raw MIME input. It prefers the primary plain
text body, falls back to HTML text, and excludes attachments. It does not fetch
links or images, execute HTML, OCR attachments, or classify every forwarded
message/alternative separately. Selected decoded headers and the body are
explicitly marked as untrusted evidence. The resulting state is bounded by
`max_text_chars`; truncated JSON-shaped evidence is still a plain text state.

Bodies and credentials are not included in CLI results or provider error
messages. A successful result includes a SHA-256 digest for correlation, which
may itself be identifying metadata. Enabling a remote backend sends selected
mail content to that provider. Prompt separation is defense in depth, not a
promise that malicious mail cannot influence a classifier.

`filter` removes every incoming `X-Clef-*` header and continuation, then adds
verdict, action, score, and score-kind headers. Original non-reserved headers,
folding, MIME body, and line endings are preserved rather than reserialized.
An existing signature that covers a removed reserved header can still be
invalidated. Integrate after inbound signature verification and before outbound
signing where applicable. Downstream rules must trust only mail processed through
this stripping boundary. Do not trust a preexisting `X-Clef-Action` header.

## Extending the backend contract

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
The engine has no cache, circuit breaker, persistent queue, or per-recipient
policy yet. Those belong in the subsequent long-running integration layer.

## Postfix / Dovecot integration boundary

The included `examples/clef-junk.sieve` files mail into Junk **only** when the
trusted action is `junk`; observe mode never triggers it. It does not replace a
user's existing Sieve script. Inspect and merge script ordering before installing.

Keep existing antivirus/antispam filters. To connect this project to mail flow,
choose an after-queue adapter with defined failure handling. An SMTP or LMTP proxy
must preserve the envelope, Bcc, per-recipient results, retry behavior, and queue
ownership. The byte-stream CLI is not an LMTP server and must not be configured
as a Postfix delivery transport by itself. No success response may be sent before
the next queue or delivery agent accepts responsibility for the message.

Evaluate observe-only results against labeled spam **and ham** first. Enable
`observe_only: false` only after choosing a threshold and deciding whether
inference failures should deliver unclassified or defer. No live mail-server
configuration is altered by installation.

## Development

```sh
python3 -m unittest discover -s tests -v
```

Tests use synthetic mail and a loopback HTTP fixture; no provider keys or
mail-server access is needed. They exercise score validation, configuration,
fallback/failure policy, MIME handling, spoofed headers, response size bounds,
timeouts, and authentication behavior.

Upstream contracts:
[Workers AI Clef](https://developers.cloudflare.com/workers-ai/models/clef/),
[Clef decision-head inference](https://huggingface.co/Cloudflare/clef),
[Postfix content inspection](https://www.postfix.org/CONTENT_INSPECTION_README.html).
