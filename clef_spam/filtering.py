"""Add delivery-policy headers without reserializing MIME or signed headers.

This is a byte-stream filter, not a delivery agent. The caller owns queuing,
recipient validation, and SMTP/LMTP acknowledgements.
"""
from .errors import InputError


def annotate(raw: bytes, result: dict) -> bytes:
    boundary = b'\r\n\r\n' if b'\r\n\r\n' in raw else b'\n\n'
    if boundary not in raw:
        raise InputError("filter requires a complete message with a header/body separator")
    headers, body = raw.split(boundary, 1)
    newline = boundary[:len(boundary)//2]
    kept = []
    dropping = False
    # Strip the reserved namespace and continuations; do not trust sender verdicts.
    for line in headers.split(newline):
        if line[:1] not in (b' ', b'\t'):
            dropping = line.split(b':', 1)[0].lower().startswith(b'x-clef-')
        if not dropping:
            kept.append(line)
    values = {
        'X-Clef-Verdict': result['verdict'],
        'X-Clef-Action': result['action'],
        'X-Clef-Score': format(result['classification']['spam_score'], '.6f'),
        'X-Clef-Score-Kind': result['classification']['score_kind'],
    }
    added = []
    for name, value in values.items():
        value = str(value)
        if '\r' in value or '\n' in value:
            raise InputError("unsafe classification header value")
        added.append((name + ': ' + value).encode('ascii'))
    return newline.join(added + kept) + boundary + body
