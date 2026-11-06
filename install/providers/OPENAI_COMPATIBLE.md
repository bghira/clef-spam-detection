# OpenAI-compatible chat APIs

Use `openai_compatible` for an ordinary chat model that supports chat completions
and JSON mode. This backend returns a **reported score**, not a native Clef
probability. For Clef itself, choose [Workers AI](CLOUDFLARE.md) or
[SystemOne](SYSTEMONE.md).

Configure `backends.chat_api`:

```json
{
  "type": "openai_compatible",
  "disabled": true,
  "options": {
    "endpoint": "https://api.example.com/v1/chat/completions",
    "model": "YOUR_MODEL",
    "api_key_env": "CHAT_API_KEY",
    "timeout_seconds": 15
  }
}
```

The server must accept `temperature: 0` and
`response_format: {"type": "json_object"}`. Its response must contain JSON
`{"spam_score": number}` in the first message, with `finish_reason: "stop"`.
Incomplete responses, refusals, or invalid scores fail explicitly.

Provide [credentials](../CREDENTIALS.md), enable the entry, and select `["chat_api"]`
in `backend_order`. By default, reported scores yield an uncertain verdict.
Set `policy.allow_reported_scores: true` only after evaluating that model's scores.
See [policy](../../docs/CONFIGURATION.md#policy).
