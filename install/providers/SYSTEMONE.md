# Self-hosted SystemOne

Use `systemone` for a Clef server that accepts `model`, `state`, and typed
`questions`, and returns a direct `answers` object. The adapter asks one `noul`
question and reads its native probability.

Configure `backends.self_hosted_clef`:

```json
{
  "type": "systemone",
  "disabled": true,
  "options": {
    "endpoint": "http://127.0.0.1:30000/v1/systemone",
    "model": "Cloudflare/clef",
    "timeout_seconds": 15
  }
}
```

Use the full endpoint URL and the model name accepted by your server. Add
`api_key_env` and optionally `api_key_env_file` if it requires bearer authentication.
HTTPS is required outside loopback.

Enable the entry and select `["self_hosted_clef"]` in `backend_order`, then run the
[installation check](../README.md#check-and-use). Model serving is managed separately.

Upstream: [Clef serving instructions](https://huggingface.co/Cloudflare/clef).
