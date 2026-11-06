"""Bounded JSON HTTP; never expose request secrets or provider error bodies."""
import json
import os
import socket
from urllib import request, error, parse
from ..config import number, text
from ..errors import (ConfigError, AuthenticationError, RateLimitError,
                      BackendUnavailable, BackendTimeout, InvalidResponse, UnsupportedCapability)

MAX_RESPONSE = 1048576

class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Do not forward credentials to a redirect target.
        return None


def endpoint(url):
    text(url, "endpoint")
    if any(ord(char) <= 32 or ord(char) == 127 for char in url):
        raise ConfigError("endpoint must not contain whitespace or control characters")
    try:
        parts = parse.urlsplit(url)
        _ = parts.port
    except ValueError:
        raise ConfigError("invalid endpoint host or port") from None
    if (parts.scheme not in {"http", "https"} or not parts.hostname or
            parts.username is not None or parts.password is not None or parts.query or parts.fragment):
        raise ConfigError("endpoint must be an HTTP(S) URL without credentials, query, or fragment")
    if parts.scheme == "http" and parts.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ConfigError("non-loopback endpoints require HTTPS")
    return url


def post(url, payload, key_env, timeout):
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if key_env:
        token = os.environ.get(key_env)
        if not token or any(ord(c) < 32 or ord(c) == 127 for c in token):
            raise AuthenticationError("configured API key environment variable is unset")
        headers["Authorization"] = "Bearer " + token
    req = request.Request(url, json.dumps(payload, allow_nan=False).encode(), headers, method="POST")
    try:
        with request.build_opener(NoRedirect()).open(req, timeout=timeout) as response:
            body = response.read(MAX_RESPONSE + 1)
        if len(body) > MAX_RESPONSE:
            raise InvalidResponse("provider response exceeds size limit")
        result = json.loads(body)
        if not isinstance(result, dict):
            raise InvalidResponse("provider response must be an object")
        return result
    except error.HTTPError as exc:
        status = exc.code
        exc.close()
        if status in {401, 403}:
            raise AuthenticationError("provider rejected authentication") from None
        if status == 429:
            raise RateLimitError("provider rate limit exceeded") from None
        if status >= 500:
            raise BackendUnavailable("provider temporarily unavailable") from None
        if status in {404, 405, 422}:
            raise UnsupportedCapability("provider rejected endpoint or request schema") from None
        raise InvalidResponse(f"provider returned HTTP {status}") from None
    except (TimeoutError, socket.timeout):
        raise BackendTimeout("provider request timed out") from None
    except error.URLError as exc:
        if isinstance(exc.reason, (TimeoutError, socket.timeout)):
            raise BackendTimeout("provider request timed out") from None
        raise BackendUnavailable("provider connection failed") from None
    except (ValueError, UnicodeError):
        raise InvalidResponse("provider returned invalid JSON") from None


def common(options):
    model = text(options.get("model"), "model")
    key = options.get("api_key_env")
    if key is not None:
        text(key, "api_key_env")
    timeout = number(options.get("timeout_seconds", 15), "timeout_seconds", 0.1, 120)
    return model, key, timeout
