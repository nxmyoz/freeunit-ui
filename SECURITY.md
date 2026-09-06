# Security policy

## Trust model

FreeUnit UI talks to the FreeUnit control API, which is a **root-equivalent interface**. A
configuration document can define an application with an arbitrary `executable` and `user`, so
the ability to write configuration is the ability to execute code. Read access alone discloses
the complete server configuration.

This project therefore assumes:

1. **The interface is not internet facing.** It binds to loopback by default and ships no
   authentication of its own. Authentication and authorisation are delegated to a reverse proxy.
2. **The process is privileged.** Since FreeUnit 1.36.0 the UNIX control socket rejects peers
   whose effective UID is neither root nor the user unitd runs as, so this process necessarily
   runs as one of them. Compromise of this process is compromise of unitd.
3. **Only trusted operators reach it.** There is no multi-user model, no per-user permissions
   and no audit log in this release.

If you cannot satisfy points 1 and 3, do not deploy this.

## Design decisions that follow from that

- The client issues `GET` requests only. Write support is absent from the code rather than
  disabled by a flag.
- No JavaScript is served, which lets the Content-Security-Policy be `default-src 'none'` with
  no `script-src` allowance at all.
- No session cookie and no secret key, because there is no session state.
- Configuration path segments from URLs are validated, not escaped: empty and relative segments
  are rejected before a control API path is built.
- Responses are sent with `Cache-Control: no-store`, since pages contain server configuration.

## Supported versions

Pre-1.0, only the latest release receives fixes.

## Reporting a vulnerability

Please report privately to **v@9dt.de** rather than opening a public issue.

Include the version, your deployment shape (proxy, control socket type), and enough detail to
reproduce. We aim to acknowledge within 72 hours and to agree a disclosure timeline with you;
the default is coordinated disclosure once a fix is available.

Please do not test against systems you do not own.
