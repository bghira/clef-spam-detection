"""Optional, lazy Clef decision-head inference, not text generation."""
import importlib.util
import re
import sys
from threading import Lock
from ..config import keys, text, number
from ..contracts import BackendCapabilities, ScoreKind
from ..errors import ConfigError, BackendUnavailable
from .remote import decision_payload, native_result

class Transformers:
    capabilities = BackendCapabilities(ScoreKind.NATIVE_PROBABILITY, local=True)

    def __init__(self, options):
        keys(options, {"model", "revision", "device", "dtype", "max_length", "trust_remote_code"}, "transformers options")
        self.model_id = text(options.get("model"), "model")
        self.revision = text(options.get("revision"), "revision")
        if not re.fullmatch(r"[a-f0-9]{40}", self.revision):
            raise ConfigError("Transformers revision must be a pinned 40-character commit SHA")
        if options.get("trust_remote_code") is not True:
            raise ConfigError("Clef's custom decision head requires trust_remote_code=true")
        self.device = text(options.get("device", "cuda"), "device")
        self.dtype = options.get("dtype", "bfloat16")
        if self.dtype not in {"bfloat16", "float16", "float32"}:
            raise ConfigError("unsupported Transformers dtype")
        self.max_length = number(options.get("max_length", 16384), "max_length", 256, 65536)
        if type(self.max_length) is not int:
            raise ConfigError("max_length must be an integer")
        self.loaded = None
        self.lock = Lock()

    def _load(self):
        import torch
        from huggingface_hub import snapshot_download
        from pathlib import Path
        path = Path(snapshot_download(self.model_id, revision=self.revision))
        name = "_clef_schema_" + self.revision
        spec = importlib.util.spec_from_file_location(name, path / "joint_schema_model.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        model, processor = module.load_release_model(path, device=self.device, dtype=getattr(torch, self.dtype))
        model.eval()
        self.loaded = (torch, module, model, processor)

    def classify(self, request):
        with self.lock:
            try:
                if self.loaded is None:
                    self._load()
                torch, module, model, processor = self.loaded
                with torch.inference_mode():
                    result = module.systemone(model, processor, decision_payload(self.model_id, request), max_length=self.max_length)
                # Upstream encoder may silently truncate state to its token budget.
                encoded = module.encode_record(processor.tokenizer, decision_payload(self.model_id, request),
                                               max_length=self.max_length, processor=processor)
                full = module.encode_record(processor.tokenizer, decision_payload(self.model_id, request),
                                            max_length=10000000, processor=processor)
                result["truncated"] = len(encoded.input_ids) < len(full.input_ids)
                return native_result(result, self.model_id)
            except ImportError:
                raise BackendUnavailable("local model requires the transformers optional dependencies") from None
            except (OSError, RuntimeError, AttributeError, ValueError):
                raise BackendUnavailable("local Clef loading or inference failed") from None

    def close(self):
        self.loaded = None
