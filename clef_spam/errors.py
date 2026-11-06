"""Stable errors: callers must not reinterpret failures as ham."""
class ClefError(Exception):
    code = "error"

class ConfigError(ClefError):
    code = "configuration"

class InputError(ClefError):
    code = "input"

class BackendError(ClefError):
    code = "backend"
    retryable = False

class AuthenticationError(BackendError):
    code = "authentication"

class RateLimitError(BackendError):
    code = "rate_limit"
    retryable = True

class BackendUnavailable(BackendError):
    code = "unavailable"
    retryable = True

class BackendTimeout(BackendUnavailable):
    code = "timeout"

class InvalidResponse(BackendError):
    code = "invalid_response"

class UnsupportedCapability(BackendError):
    code = "unsupported_capability"

class BackendsExhausted(BackendUnavailable):
    code = "backends_exhausted"
    def __init__(self, failures):
        super().__init__("all selected backends failed; message remains unclassified")
        self.failures = failures
