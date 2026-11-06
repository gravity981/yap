# Security policy

## Reporting a vulnerability

Please do **not** open a public issue. Report it privately through GitHub: on the
repository page, *Security → Report a vulnerability*
([direct link](https://github.com/gravity981/yap/security/advisories/new)).

Include what is affected, how to reproduce it, and the version (shown in the app's footer
and at `/api/version`). You will get an answer as soon as possible; this is a spare-time
project, so it may take a few days. Fixes are released as a new patch version, and the
advisory is published once a fix is available.

## Supported versions

Only the latest release gets security fixes.

## Scope and known limits

The app is meant for a **trusted home network**:

- It is served over plain HTTP without a reverse proxy, so passwords and session cookies
  can be read by anyone who can read the network traffic. Do not expose it to the
  internet; use a VPN for remote access, or put an HTTPS reverse proxy in front of it and
  set `COOKIE_SECURE=true`.
- LLM API keys are stored encrypted with a server secret (`APP_SECRET_KEY`); anyone with
  access to both the database and the secret can read them.

Reports about these documented limits are welcome as ideas, but are not vulnerabilities.
