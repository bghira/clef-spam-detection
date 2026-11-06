import argparse
import json
import sys
from contextlib import ExitStack
from .config import load
from .engine import Classifier
from .errors import ClefError
from .filtering import annotate


def main(argv=None):
    parser = argparse.ArgumentParser(description="Classify email, filter bytes, or deliver a single Postfix recipient via LMTP.")
    parser.add_argument("--config", default="config.json", help="configuration path (default: ./config.json)")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("validate", help="validate configuration without inference or model downloads")
    for command in ("classify", "filter"):
        cmd = sub.add_parser(command, help="JSON verdict" if command == "classify" else "email with trusted policy headers")
        cmd.add_argument("message", nargs="?", default="-", help=".eml path, or - for stdin")
    deliver = sub.add_parser("deliver", help="Postfix pipe delivery for exactly one envelope recipient")
    deliver.add_argument("--sender", required=True, help="envelope sender; empty string for bounces")
    deliver.add_argument("--recipient", required=True, help="one envelope recipient, including Bcc")
    deliver.add_argument("--lmtp-socket", required=True, help="absolute Unix path to Dovecot LMTP")
    deliver.add_argument("--lmtp-timeout", type=float, default=30)
    deliver.add_argument("--max-delivery-bytes", type=int, default=536870912)
    deliver.add_argument("--failure-mode", choices=("defer", "deliver"), default="defer",
                         help="inference failure policy; delivery errors always defer")
    args = parser.parse_args(argv)
    if args.command == "deliver":
        from .delivery import run
        return run(args, sys.stdin.buffer)
    engine = None
    try:
        config = load(args.config)
        engine = Classifier(config)
        if args.command == "validate":
            out = {"valid": True, "backend_order": list(config.backend_order),
                   "observe_only": config.policy.observe_only, "ready": bool(config.backend_order)}
        else:
            with ExitStack() as stack:
                stream = sys.stdin.buffer if args.message == "-" else stack.enter_context(open(args.message, "rb"))
                raw = stream.read(config.max_message_bytes + 1)
            out = engine.classify(raw)
        if args.command == "filter":
            sys.stdout.buffer.write(annotate(raw, out))
        else:
            print(json.dumps(out, allow_nan=False))
        return 0
    except ClefError as exc:
        detail = {"code": exc.code, "message": str(exc)}
        if hasattr(exc, "retryable"):
            detail["retryable"] = exc.retryable
        if hasattr(exc, "failures"):
            detail["failures"] = exc.failures
        print(json.dumps({"error": detail}), file=sys.stderr)
        return 2 if exc.code == "configuration" else 1
    except OSError:
        print(json.dumps({"error": {"code": "io", "message": "cannot read message input"}}), file=sys.stderr)
        return 1
    finally:
        if engine is not None:
            engine.close()

if __name__ == "__main__":
    sys.exit(main())
