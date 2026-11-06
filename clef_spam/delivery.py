"""Postfix pipe delivery: classify once, forward one recipient to Unix LMTP.

Postfix owns the queue until this command exits successfully. Never use this
transport for more than one recipient per invocation.
"""
from hashlib import sha256
import json
import os
import smtplib
import syslog
import tempfile

from .config import load
from .engine import Classifier
from .errors import ClefError, ConfigError, InputError
from .filtering import annotate, annotate_unclassified

MAX_HEADER_BYTES = 262144

class DeliveryError(Exception):
    pass


def event(detail):
    # Logging must not turn confirmed delivery into a retry/duplicate.
    try:
        syslog.openlog('clef-spam', syslog.LOG_PID, syslog.LOG_MAIL)
        syslog.syslog(syslog.LOG_INFO, json.dumps(detail, allow_nan=False))
    except Exception:
        pass


def validated_address(value, allow_empty=False):
    if (not isinstance(value, str) or (not value and not allow_empty) or
            any(ord(c) < 32 or ord(c) == 127 for c in value) or
            '<' in value or '>' in value):
        raise DeliveryError('invalid envelope address')
    return value


def header_block(stream):
    parts = []
    size = 0
    while True:
        part = stream.readline(MAX_HEADER_BYTES + 1 - size)
        if not part:
            raise DeliveryError('message has no header/body separator')
        parts.append(part)
        size += len(part)
        if size > MAX_HEADER_BYTES:
            raise DeliveryError('message headers exceed delivery limit')
        if part in (b'\n', b'\r\n'):
            return b''.join(parts)


def smtp_data(chunks):
    """Stream CRLF normalization and SMTP dot stuffing across chunk boundaries."""
    start = True
    pending_cr = False
    # A bytearray keeps buffering bounded, even for hostile unbroken lines.
    out = bytearray()
    for chunk in chunks:
        for byte in chunk:
            if pending_cr:
                if byte == 10:
                    out.extend(b'\r\n')
                    start = True
                    pending_cr = False
                    continue
                out.append(13)
                pending_cr = False
                start = False
            if byte == 13:
                pending_cr = True
            elif byte == 10:
                out.extend(b'\r\n')
                start = True
            else:
                if start and byte == 46:
                    out.append(46)
                out.append(byte)
                start = False
            if len(out) >= 65536:
                yield bytes(out)
                out.clear()
    if pending_cr:
        out.append(13)
        start = False
    if not start:
        out.extend(b'\r\n')
    if out:
        yield bytes(out)
    yield b'.\r\n'


def forward(stream, headers, socket_path, sender, recipient, timeout):
    sender = validated_address(sender, allow_empty=True)
    recipient = validated_address(recipient)
    if not os.path.isabs(socket_path):
        raise DeliveryError('LMTP socket must be an absolute path')
    client = smtplib.LMTP(timeout=timeout)
    try:
        code, _ = client.connect(socket_path)
        if code != 220:
            raise DeliveryError('LMTP greeting failed')
        code, _ = client.ehlo()  # LMTP uses LHLO, not EHLO.
        if code != 250:
            raise DeliveryError('LMTP LHLO failed')
        options = ['BODY=8BITMIME'] if client.has_extn('8bitmime') else []
        try:
            (sender + recipient).encode('ascii')
            headers.decode('ascii')
        except UnicodeError:
            if not client.has_extn('smtputf8'):
                raise DeliveryError('downstream does not support SMTPUTF8') from None
            options.append('SMTPUTF8')
        code, _ = client.mail(sender, options)
        if code != 250:
            raise DeliveryError('LMTP sender was not accepted')
        code, _ = client.rcpt(recipient)
        if code not in (250, 251):
            raise DeliveryError('LMTP recipient was not accepted')
        code, _ = client.docmd('DATA')
        if code != 354:
            raise DeliveryError('LMTP DATA was not accepted')
        def chunks():
            yield headers
            while chunk := stream.read(65536):
                yield chunk
        for chunk in smtp_data(chunks()):
            client.send(chunk)
        # Exactly one final reply is expected because there is ONE recipient.
        code, _ = client.getreply()
        if code != 250:
            raise DeliveryError('LMTP delivery was not confirmed')
    finally:
        # Do not turn an unsuccessful QUIT after accepted DATA into a duplicate.
        client.close()


def run(args, source):
    engine = None
    stage = "configuration"
    try:
        config = load(args.config)
        engine = Classifier(config)
        validated_address(args.sender, allow_empty=True)
        validated_address(args.recipient)
        if args.max_delivery_bytes < 1 or args.lmtp_timeout <= 0:
            raise DeliveryError('invalid delivery size or timeout setting')
        stage = "spool"
        with tempfile.TemporaryFile() as spool:
            count = 0
            digest = sha256()
            while chunk := source.read(65536):
                count += len(chunk)
                if count > args.max_delivery_bytes:
                    raise DeliveryError('message exceeds delivery spool limit')
                digest.update(chunk)
                spool.write(chunk)
            spool.seek(0)
            detail = {'message_sha256': digest.hexdigest()}
            stage = "classification"
            try:
                result = engine.classify(spool.read(config.max_message_bytes + 1))
                detail.update(verdict=result['verdict'], action=result['action'],
                              spam_score=result['classification']['spam_score'],
                              backend=result['backend'], elapsed_ms=result['elapsed_ms'])
                failure = None
            except (ClefError, OSError) as exc:
                if args.failure_mode != 'deliver' or isinstance(exc, ConfigError):
                    raise DeliveryError('classification failed; delivery deferred') from None
                result = None
                failure = exc.code if isinstance(exc, ClefError) else 'io'
                detail.update(verdict='unclassified', action='deliver', error_code=failure)
            spool.seek(0)
            stage = "headers"
            original_headers = header_block(spool)
            filtered = annotate(original_headers, result) if result else annotate_unclassified(original_headers, failure)
            stage = "lmtp"
            forward(spool, filtered, args.lmtp_socket, args.sender, args.recipient, args.lmtp_timeout)
            event(dict(detail, status='delivered'))
        return os.EX_OK
    except Exception as exc:
        # No provider response, credential, recipient or message content in logs.
        # Defer even permanent downstream errors; let the queue retain ownership.
        event({'status': 'deferred', 'stage': stage, 'error_type': type(exc).__name__,
               'reason': str(exc) if isinstance(exc, DeliveryError) else 'classification_or_delivery_failure'})
        return os.EX_TEMPFAIL
    finally:
        if engine is not None:
            try:
                engine.close()
            except Exception:
                pass
