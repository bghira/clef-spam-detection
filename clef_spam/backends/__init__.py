"""Built-in adapters and explicit package entry point discovery."""
from importlib.metadata import entry_points
from ..contracts import Backend, BackendCapabilities, ScoreKind
from ..errors import ConfigError


def factory(kind):
    from .remote import WorkersAI, SystemOne, OpenAICompatible
    from .transformers import Transformers
    builtins = {"workers_ai": WorkersAI, "systemone": SystemOne,
                "openai_compatible": OpenAICompatible, "transformers": Transformers}
    if kind in builtins:
        return builtins[kind]
    matches = list(entry_points(group="clef_spam.backends", name=kind))
    if len(matches) != 1:
        raise ConfigError("unknown or ambiguous backend type")
    try:
        return matches[0].load()
    except Exception as exc:
        raise ConfigError("cannot load backend plugin") from exc


def build(spec) -> Backend:
    try:
        backend = factory(spec["type"])(dict(spec.get("options", {})))
    except ConfigError:
        raise
    except Exception as exc:
        raise ConfigError("backend initialization failed") from exc
    if not isinstance(backend, Backend) or not isinstance(backend.capabilities, BackendCapabilities):
        raise ConfigError("plugin does not implement Backend contract")
    if not isinstance(backend.capabilities.score_kind, ScoreKind):
        raise ConfigError("plugin must declare explicit score semantics")
    return backend
