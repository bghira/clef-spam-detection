# Ollama

For Clef, use the `systemone` backend and `/v1/systemone`. This preserves native
decision probabilities. Chat completions are for ordinary chat models; they are
not the Clef inference interface.

## Ollama Cloud

Configure `backends.ollama_cloud`:

```json
{
  "type": "systemone",
  "disabled": true,
  "options": {
    "endpoint": "https://ollama.com/v1/systemone",
    "model": "clef-flash:9b",
    "api_key_env": "OLLAMA_API_KEY",
    "timeout_seconds": 30
  }
}
```

Supply `OLLAMA_API_KEY` through the environment or an
[API credential file](../CREDENTIALS.md). Set `disabled` to `false` and
`backend_order` to `["ollama_cloud"]`. Follow the [installation check](../README.md#check-and-use).

`clef-flash:9b` selects the 9B model. Use a model identifier supported by your
Ollama Cloud account; availability is controlled by the provider.

## Local Ollama

Set `endpoint` to `http://127.0.0.1:11434/v1/systemone` and use a locally available
Clef model. Omit `api_key_env` and `api_key_env_file` for an unauthenticated local
server. This project does not install Ollama or download its models.

Upstream: [decision API](https://github.com/ollama/ollama/blob/main/docs/capabilities/decision.mdx) ·
[Clef Flash](https://ollama.com/library/clef-flash).
