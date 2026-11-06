# Configuration and CLI

Copy `config.json.example` to the ignored `config.json`. Paths passed to `--config`
are relative to the working directory unless absolute. Unknown settings and
malformed configuration are rejected.

## Backend selection

`schema_version` must be `1`. `backends` maps instance names to `type`, `disabled`,
and provider-specific `options`. All enabled instances must occur exactly once in
`backend_order`; the default is an empty list with every backend disabled.

Only retryable errors advance to the next backend: connection failures, timeouts,
rate limits, and HTTP 5xx responses. Authentication, schema, and contract errors
stop classification. Uncertain classifications do not trigger fallback.

Provider options: [Workers AI](../install/providers/CLOUDFLARE.md),
[Ollama](../install/providers/OLLAMA.md), [SystemOne](../install/providers/SYSTEMONE.md),
[Transformers](../install/providers/TRANSFORMERS.md),
[chat APIs](../install/providers/OPENAI_COMPATIBLE.md).

## Policy

`question` is configurable, but **yes must mean spam**. The default asks whether
an email is spam or phishing; reversing the question would reverse the score's
meaning. Clef uses the native `noul` probability, not `choice.confidence`.
Chat-model scores are marked `reported_score` and are not treated as equivalent.
A probability threshold is not a guarantee of a particular false-positive rate;
evaluate labeled spam and ham before enabling routing.

| `policy` setting | Default | Meaning |
| --- | --- | --- |
| `spam_threshold` | `0.98` | At or above: spam |
| `ham_threshold` | `0.1` | At or below: ham; between thresholds: uncertain |
| `observe_only` | `true` | Emit `action: observe` for successful classifications |
| `allow_reported_scores` | `false` | Otherwise chat scores produce an uncertain verdict |
| `allow_truncated_input` | `false` | Otherwise known-truncated evidence produces an uncertain verdict |

The ham threshold must be lower than the spam threshold. With observation disabled,
spam produces `action: junk`; ham and uncertain produce `action: deliver`. Policy
is global per config, not per recipient. Inference errors do not invent a ham score.

## Input limits

`input.max_message_bytes` defaults to 2 MiB; oversized classification input is
rejected. `input.max_text_chars` defaults to 16,000; exceeding it marks evidence
as truncated. See [message handling](MESSAGE_HANDLING.md) and the separate
[delivery limits](../install/smtp/postfix/DELIVERY.md).

## Commands and output

```sh
clef-spam --config config.json validate
clef-spam --config config.json classify message.eml
clef-spam --config config.json classify < message.eml
clef-spam --config config.json filter message.eml > filtered.eml
```

`validate` performs no inference or credential-file reads. `classify` emits JSON
with `schema_version`, `message_sha256`, `backend`, `classification`,
`input_truncated`, `verdict`, `reason`, `action`, `observe_only`, `elapsed_ms`, and
`fallback_errors`. `classification` contains `spam_score`, `score_kind`, `model`,
and the backend's truncation flag. The top-level flag also includes preprocessing
truncation. `reason` explains the threshold or reason for abstention.

`filter` emits the email with trusted `X-Clef-*` headers; it does not deliver it.
Write to a new file and check the exit status before using the result: redirection
can leave an empty file on failure. Errors are JSON on stderr. Exit codes are
0 for success, 2 for configuration errors, and 1 for input/backend/I/O errors.
The separate [`deliver` command](../install/smtp/postfix/DELIVERY.md) uses Postfix
queue semantics and returns 75 when delivery must be retried.
