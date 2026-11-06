# Installation

Requires Python 3.11+. HTTP inference and Postfix delivery use the standard library.
Only local Transformers inference needs optional dependencies.

```sh
git clone https://github.com/bghira/clef-spam-detection.git
cd clef-spam-detection
python3 -m venv .venv
.venv/bin/pip install .
cp config.json.example config.json
```

For development, use `pip install -e .` instead.

## Configure a provider

Start with [Cloudflare Workers AI](providers/CLOUDFLARE.md), or choose
[Ollama](providers/OLLAMA.md), [SystemOne](providers/SYSTEMONE.md),
[Transformers](providers/TRANSFORMERS.md), or a
[chat API](providers/OPENAI_COMPATIBLE.md).

Each guide describes an entry under `backends`. In your ignored `config.json`:

1. Fill in that entry's options and set `disabled` to `false`.
2. Put its name in `backend_order`, for example `["cloudflare"]`.
3. Supply its API key via the named environment variable or a
   [credential file](CREDENTIALS.md).

Every enabled backend must appear once in `backend_order`. Additional entries are
ordered fallbacks for retryable failures; they are not queried as an ensemble.
An omitted `disabled` means disabled. All example entries are disabled by default.

## Check and use

```sh
.venv/bin/clef-spam --config config.json validate
.venv/bin/clef-spam --config config.json classify message.eml
```

Validation performs no inference, downloads, or credential-file reads. `ready`
is false until a backend is selected. Classification sends selected email content
to the configured provider; use synthetic mail for your first check.

Keep `observe_only: true` while evaluating spam and ham. See the
[configuration reference](../docs/CONFIGURATION.md) for thresholds and commands.

For server deployment, continue with [Postfix + Dovecot](smtp/postfix/README.md).
