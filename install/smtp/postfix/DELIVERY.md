# Pipe delivery semantics

`clef-spam deliver` spools input to a private temporary file, classifies bounded
evidence, replaces reserved headers, and streams the message to a Unix LMTP
socket. It is a client, not a listener. The default Postfix wiring is in the
[setup guide](README.md).

## Queue ownership

Success is returned only after Dovecot confirms DATA delivery for the single
`--recipient`. Envelope Bcc recipients and empty bounce senders are preserved.
Postfix splits multiple recipients into separate invocations; each currently
makes its own inference request.

| Condition | Result |
| --- | --- |
| Confirmed Dovecot delivery | Exit 0 |
| Inference error with `--failure-mode=defer` (default) | Exit 75; retain in queue |
| Inference error with `--failure-mode=deliver` | Forward unclassified, without a fabricated score |
| Invalid config, malformed headers/envelope, or spool failure | Exit 75 |
| Any downstream delivery failure, including a permanent LMTP reply | Exit 75 |

Postfix's queue lifetime bounds retries. Connection loss after downstream
acceptance but before acknowledgement can produce duplicate delivery on retry;
SMTP/LMTP is not an exactly-once protocol. A failed QUIT after accepted DATA is
not treated as failed delivery.

## Limits

- Delivery spool: 512 MiB by default (`--max-delivery-bytes`). Set it above
  Postfix's message size limit, allowing for added headers.
- Classification input: independently bounded, 2 MiB by default. Larger messages
  can pass unclassified under the `deliver` inference-failure policy.
- Headers: 256 KiB. Disk spooling and bounded buffers avoid loading large
  attachments into memory; allow sufficient temporary disk space per process.
- LMTP I/O timeout: 30 seconds (`--lmtp-timeout`). Envelopes/headers requiring
  SMTPUTF8 defer if Dovecot does not advertise support.

The pipe process limit must exceed inference plus delivery time. A killed or
failed pipe never reports successful delivery. Use the `clef-spam` syslog tag
(mail facility) to inspect classified/unclassified decisions and delivery status.
