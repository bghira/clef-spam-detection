"""Read a named credential without sourcing files or mutating os.environ."""
import os
import re
import shlex
import stat

from .errors import AuthenticationError

MAX_ENV_BYTES = 65536
VARIABLE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")


def parse_env(contents: str) -> dict[str, str]:
    """Small literal assignment format, not a shell/environment.d interpreter.

    Accept KEY=value, optional export, single/double quotes and # comments.
    Expansion and command substitution are never performed. Reject expansion
    syntax explicitly so a template cannot silently become an invalid token.
    Error messages must never contain source lines, variable values, or paths.
    """
    values = {}
    for line in contents.splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        if line.startswith('export '):
            line = line[7:].lstrip()
        name, sep, value = line.partition('=')
        name = name.strip()
        if not sep or not VARIABLE.fullmatch(name) or name in values:
            raise AuthenticationError('invalid or duplicate credential file assignment')
        try:
            parts = [] if value.lstrip().startswith('#') else shlex.split(value, comments=False, posix=True)
        except ValueError:
            raise AuthenticationError('invalid credential file quoting') from None
        if len(parts) > 1 and not parts[1].startswith('#'):
            raise AuthenticationError('credential file values must be single-line literals')
        literal = parts[0] if parts else ''
        if re.search(r'\$[A-Za-z_{(]|`', literal):
            raise AuthenticationError('credential file expansions are not supported')
        values[name] = literal
    return values


def read_env_file(path: str) -> dict[str, str]:
    """Only regular files owned by root/current user, without public access.

    Group read is allowed. Group/other writes, symlinks, special files and
    oversized files are rejected before reading any file data.
    """
    try:
        flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
        fd = os.open(path, flags)
        with os.fdopen(fd, 'rb') as stream:
            info = os.fstat(stream.fileno())
            if (not stat.S_ISREG(info.st_mode) or
                    info.st_uid not in {0, os.geteuid()} or
                    info.st_mode & 0o027 or info.st_size > MAX_ENV_BYTES):
                raise AuthenticationError('credential file ownership, permissions, type, or size is unsafe')
            data = stream.read(MAX_ENV_BYTES + 1)
        if len(data) > MAX_ENV_BYTES:
            raise AuthenticationError('credential file exceeds size limit')
        return parse_env(data.decode('utf-8-sig'))
    except (OSError, UnicodeError):
        raise AuthenticationError('cannot read credential file') from None


def api_key(name: str, env_file: str | None = None) -> str:
    if not isinstance(name, str) or not VARIABLE.fullmatch(name):
        raise AuthenticationError('invalid API key variable name')
    # A configured file is authoritative; do not fall back to an ambient key.
    value = read_env_file(env_file).get(name) if env_file is not None else os.environ.get(name)
    if not value or any(ord(c) <= 32 or ord(c) == 127 for c in value):
        raise AuthenticationError('API key variable is missing, empty, or invalid')
    return value
