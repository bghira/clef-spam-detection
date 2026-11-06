# Postfix + Dovecot

Use the Postfix pipe transport for final delivery to virtual mailboxes:

```text
Existing content filters → Postfix queue → Clef pipe → Dovecot LMTP → Sieve
```

Postfix retains queue responsibility until Dovecot confirms delivery. Existing
Amavis/antivirus filtering stays ahead of Clef; outgoing remote SMTP mail keeps
its existing transport. The supplied templates assume Dovecot 2.3 with Pigeonhole.

## 1. Install and configure Clef

Follow [installation](../../README.md), using
`/data/scripts/clef-spam-detection` as the deployment directory to match the
templates. A different location requires updating `master.cf` below. Install the
package in that directory's `.venv`, not just in the development checkout.

Create a dedicated account if it does not already exist:

```sh
sudo useradd --system --user-group --no-create-home --shell /usr/sbin/nologin clef-spam
```

Keep deployed code root-owned, with read/traverse access for the service account.
Use `root:clef-spam`, mode `0750`, for the deployment directory and `0640` for
`config.json`. Parent directories must permit traversal. The account also needs
read-only access to its [credential file](../../CREDENTIALS.md), not to mailbox
files or Postfix's private directory.

Configure [Cloudflare Workers AI](../../providers/CLOUDFLARE.md) or another provider,
keep `observe_only: true`, and validate as the service account:

```sh
sudo -u clef-spam /data/scripts/clef-spam-detection/.venv/bin/clef-spam \
  --config=/data/scripts/clef-spam-detection/config.json validate
```

Use HTTP inference here. The pipe starts a process per delivery, so loading local
Transformers weights for every message is impractical.

## 2. Back up and merge configuration

Back up Postfix `main.cf` / `master.cf`, the affected Dovecot files, and any existing
Sieve before-script settings before editing them. Retain the old direct delivery
transport for rollback.

| Template | Merge into |
| --- | --- |
| [main.cf](main.cf) | `/etc/postfix/main.cf` |
| [master.cf](master.cf) | `/etc/postfix/master.cf` |
| [dovecot.conf](dovecot.conf) | Dovecot configuration, e.g. `conf.d/95-clef-spam.conf` |
| [clef-junk.sieve](clef-junk.sieve) | `/etc/dovecot/sieve/clef-junk.sieve` |

**`clef_destination_recipient_limit = 1` is required.** The transport accepts one
recipient and one final LMTP response. The sample permits two simultaneous
invocations and uses a 120-second process limit. Match limits to your provider
latency and [delivery requirements](DELIVERY.md).

The Dovecot template adds a `clef-lmtp` Unix listener under Dovecot's base directory
(`/run/dovecot` in the Postfix template). Its `0600` permissions grant access only
to `clef-spam`. Preserve existing LMTP listeners and Sieve settings. If
`sieve_before` is already in use, choose the next numbered before-script slot.
The Sieve source and compiled binary must be readable by Dovecot's mail user.

## 3. Validate and reload

From the deployed project directory, after installing the reviewed templates:

```sh
sudo sievec /etc/dovecot/sieve/clef-junk.sieve
sudo doveconf -n
sudo postfix check
```

Reload Dovecot first and verify `/run/dovecot/clef-lmtp` exists with the expected
owner and permissions. Reload Postfix only after that listener is ready:

```sh
sudo systemctl reload dovecot
sudo stat /run/dovecot/clef-lmtp
sudo systemctl reload postfix
```

Deliver a marked synthetic message to a mailbox you control. Confirm it passes
existing content filters, has regenerated `X-Clef-*` headers, and appears in the
expected mailbox. Review `journalctl -t clef-spam` or your mail log, and check
`postqueue -p` for deferred delivery.

## 4. Review before Junk routing

Observation records verdicts but leaves delivery decisions to existing rules.
Evaluate labeled spam and ham, choose thresholds, then set `policy.observe_only`
to `false` in Clef's config to let the installed Sieve rule act on `action: junk`.
Each pipe invocation reloads config, so a policy edit needs no Postfix reload.

The sample uses `--failure-mode=deliver`: failed inference is logged and delivered
unclassified. Dovecot failures always defer. See [delivery semantics](DELIVERY.md).

## Rollback

Restore the saved Postfix main/master configuration, validate, and reload Postfix.
Once routing uses the original direct delivery transport again, remove Clef's
added Dovecot listener/Sieve hook and reload Dovecot. Keep the original listener
available throughout the migration. Deferred mail remains in Postfix's queue.
