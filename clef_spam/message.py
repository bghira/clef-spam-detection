from dataclasses import dataclass
from email import policy
from email.parser import BytesParser
from hashlib import sha256
from html.parser import HTMLParser
import json
from .errors import InputError

class VisibleText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hidden = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.hidden += 1
        if tag in {"br", "p", "div", "li", "tr"} and not self.hidden:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)

@dataclass(frozen=True)
class PreparedMessage:
    state: str
    digest: str
    truncated: bool


def prepare(raw: bytes, max_bytes: int, max_chars: int) -> PreparedMessage:
    if len(raw) > max_bytes:
        raise InputError("message exceeds max_message_bytes")
    if not raw.strip():
        raise InputError("message is empty")
    try:
        msg = BytesParser(policy=policy.default).parsebytes(raw)
        body = msg.get_body(preferencelist=("plain", "html"))
        content = body.get_content() if body else ""
        if not isinstance(content, str):
            content = ""
        if body and body.get_content_type() == "text/html":
            parser = VisibleText()
            parser.feed(content)
            content = "".join(parser.parts)
        # Bound each header before serializing; duplicated headers stay lists.
        headers = {h: [str(v) for v in msg.get_all(h, [])]
                   for h in ("From", "To", "Cc", "Reply-To", "Subject", "Date")}
        state = json.dumps({"untrusted_headers": headers, "untrusted_body": content}, ensure_ascii=False)
        state = state.replace("\x00", "")
    except Exception as exc:
        raise InputError("message cannot be decoded") from exc
    # A text state may be cut mid-JSON: it is model evidence, not a JSON API object.
    return PreparedMessage(state[:max_chars], sha256(raw).hexdigest(), len(state) > max_chars)
