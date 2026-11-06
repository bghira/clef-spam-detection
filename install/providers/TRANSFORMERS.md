# Hugging Face Transformers

The optional `transformers` backend loads Clef's backbone and custom joint schema
head, returning native decision probabilities. It does not use text generation.

```sh
.venv/bin/pip install '.[transformers]'
```

Configure `backends.local_clef`:

```json
{
  "type": "transformers",
  "disabled": true,
  "options": {
    "model": "Cloudflare/clef",
    "revision": "REPLACE_WITH_MODEL_COMMIT_SHA",
    "device": "cuda",
    "dtype": "bfloat16",
    "max_length": 16384,
    "trust_remote_code": false
  }
}
```

Review `joint_schema_model.py` at the chosen revision. Pin its immutable
40-character commit SHA and explicitly set `trust_remote_code: true` to permit
execution of that code. Enable the entry and select `["local_clef"]` in
`backend_order`.

Model loading/downloads happen lazily during classification. A reusable
`Classifier` loads once and serializes local calls; a CLI process per message
reloads the model, so this backend is not suitable for the current Postfix pipe
transport without a separate persistent serving layer.

There is no preemptive inference deadline, quantization, or CPU-offload layer.
Ensure sufficient GPU memory and compatible optional libraries. The adapter is
fixture-tested; full-weight GPU inference has not been validated by this project.

Upstream: [Clef model and inference code](https://huggingface.co/Cloudflare/clef).
