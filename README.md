# clef-spam-detection

Classify email with Cloudflare Clef and route high-confidence spam to Junk through
Dovecot Sieve. Cloudflare Workers AI is the primary provider; adapters also support
Ollama, self-hosted Clef, local Transformers inference, and compatible chat APIs.

Python 3.11+. The core, HTTP providers, and Postfix transport have no third-party
runtime dependencies. Classification starts in **observe mode** so you can review
results before enabling Junk routing.

## Get started

```sh
python3 -m venv .venv
.venv/bin/pip install .
cp config.json.example config.json
```

[Configure Cloudflare Workers AI](install/providers/CLOUDFLARE.md), then check your
configuration and classify an email:

```sh
.venv/bin/clef-spam --config config.json validate
.venv/bin/clef-spam --config config.json classify message.eml
```

All providers in `config.json.example` are disabled. Enable one and select it in
`backend_order`; keep credentials outside Git. See [installation](install/README.md)
and [credential files](install/CREDENTIALS.md).

## Providers

- [Cloudflare Workers AI](install/providers/CLOUDFLARE.md) — native Clef and Clef Flash.
- [Ollama](install/providers/OLLAMA.md) — native Clef through SystemOne.
- [Self-hosted SystemOne](install/providers/SYSTEMONE.md).
- [Hugging Face Transformers](install/providers/TRANSFORMERS.md).
- [OpenAI-compatible chat APIs](install/providers/OPENAI_COMPATIBLE.md) — reported scores, not native Clef probabilities.

## Mail-server integration

- [Postfix + Dovecot](install/smtp/postfix/README.md) — pipe transport, LMTP delivery, and Sieve templates.
- [Exim](install/smtp/exim/README.md) — integration status and requirements.

## Reference and development

[Configuration and CLI](docs/CONFIGURATION.md) · [Backend contracts](docs/BACKENDS.md) ·
[Message handling and limits](docs/MESSAGE_HANDLING.md)

```sh
python3 -m unittest discover -s tests -v
```
