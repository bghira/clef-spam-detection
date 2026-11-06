# Exim integration status

An Exim integration has not been implemented or validated. The supported
mail-server recipe is currently [Postfix + Dovecot](../postfix/README.md).

The standalone `classify` and `filter` commands can be used for offline evaluation.
They do not deliver mail, so a pipe to `filter` alone is not a delivery transport.

A future Exim adapter needs a reviewed pipe/router configuration, exactly one
envelope recipient per invocation, empty-sender handling, temporary-failure
mapping, and confirmation of downstream LMTP acceptance before acknowledging the
message. It also needs the same trusted-header boundary before Sieve routing.
No Exim configuration is installed or implied by this directory.
