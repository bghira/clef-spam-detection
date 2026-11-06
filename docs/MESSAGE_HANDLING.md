# Message handling and limits

## Evidence

The parser prefers the primary plain text body, falls back to HTML text, and
excludes attachments. It does not fetch links/images, execute HTML, OCR files,
or classify every forwarded message or MIME alternative separately. Selected
decoded headers and the body are marked as untrusted evidence. Prompt separation
reduces ambiguity but does not guarantee resistance to malicious instructions.

Raw messages are size-checked before parsing. Prepared text is bounded separately;
a truncated JSON-shaped state remains plain text evidence. Remote truncation is
recognized only when the provider reports it. Character limits do not substitute
for a model's token limit. The local adapter also checks its encoder token budget.

## Trust boundary

`filter` and `deliver` strip every incoming `X-Clef-*` header and continuation,
then add their own verdict and action. Successful classifications also include
score and score kind; delivery after an inference failure is marked unclassified.
Sieve must trust only messages that passed this stripping boundary.

Non-reserved header folding and MIME body bytes are preserved by the filter;
LMTP delivery performs normal SMTP newline normalization and dot stuffing. Removing
a reserved header can invalidate a signature that covered it. Place filtering
after inbound signature verification and before outbound signing where applicable.

## Privacy and transport limits

Remote providers receive selected mail content. CLI results and standard error
messages omit bodies, credentials and provider error bodies. Message digests are
correlation metadata and can themselves be identifying. The delivery log uses the
`clef-spam` syslog tag and mail facility without envelope addresses or bodies.

HTTP verifies system TLS certificates, refuses redirects, limits responses to
1 MiB, and permits plaintext only on loopback. `timeout_seconds` is a socket I/O
timeout, not a hard total deadline against a slowly streaming server. The Postfix
transport has a separate process time limit. There are no automatic HTTP retries,
backoff, shared verdict cache, or circuit breaker.
