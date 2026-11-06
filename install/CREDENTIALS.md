# API credentials

HTTP backends read the variable named by `api_key_env` from the process environment.
To read it from a file instead, also configure an absolute `api_key_env_file`:

```json
{
  "api_key_env": "CLOUDFLARE_API_TOKEN",
  "api_key_env_file": "/etc/clef-spam/credentials.env"
}
```

The file is authoritative: a missing key or unreadable file causes an error,
without falling back to the process environment. It is reopened on each request
so rotations take effect without restarting a reusable classifier. Initialization
and `validate` never read it.

## File format

```sh
# Literal assignments; single or double quotes are optional.
CLOUDFLARE_API_TOKEN="replace-with-your-token"
```

Blank lines, comments, optional `export`, embedded `=` / `#` characters, and
whitespace-separated trailing comments are supported. Duplicate keys, multiline
values, malformed lines, variable expansion, and command substitution are rejected.
The loader neither executes the file nor exports its values. This is a literal
assignment subset, not a shell or full systemd environment.d interpreter.

## Permissions

Use `0600` for a process-owned file, or `0640 root:clef-spam` for a root-managed
file read by the service account. Its parent directories must permit traversal.
The account needs read access, not ownership or write access.

```sh
sudo chown root:clef-spam /etc/clef-spam/credentials.env
sudo chmod 0640 /etc/clef-spam/credentials.env
```

Files must be regular, owned by root or the process user, and at most 64 KiB.
Symlinks, public access, and group/other writes are rejected. Keep files outside
the repository; `config.json` is ignored and should contain only credential
references. Errors never include the file contents or API key.
