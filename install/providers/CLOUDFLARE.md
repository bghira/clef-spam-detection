# Cloudflare Workers AI

Cloudflare's hosted implementation is the primary Clef provider. The `workers_ai`
adapter calls its account REST API and unwraps the `success` / `result` response.
It returns the native `noul` probability that the configured question is true.

## Configure

Fill in `backends.cloudflare` in `config.json`:

```json
{
  "type": "workers_ai",
  "disabled": true,
  "options": {
    "account_id": "YOUR_ACCOUNT_ID",
    "model": "clef",
    "api_key_env": "CLOUDFLARE_API_TOKEN",
    "timeout_seconds": 15
  }
}
```

Use `clef` for the 27B model or `clef-flash` for the faster 9B model. The adapter
constructs `/client/v4/accounts/{account_id}/ai/run/@cf/cloudflare/{model}`;
no endpoint override is needed.

Provide a Cloudflare API token authorized to run Workers AI on that account via
`CLOUDFLARE_API_TOKEN`, or add `api_key_env_file` as described in
[credentials](../CREDENTIALS.md).

Set `disabled` to `false` and `backend_order` to `["cloudflare"]`, then:

```sh
.venv/bin/clef-spam --config config.json validate
.venv/bin/clef-spam --config config.json classify message.eml
```

Keep observation enabled while evaluating the threshold. The installation needs
no Cloudflare SDK or deployed Worker.

Upstream: [Clef](https://developers.cloudflare.com/workers-ai/models/clef/) ·
[Clef Flash](https://developers.cloudflare.com/workers-ai/models/clef-flash/).
