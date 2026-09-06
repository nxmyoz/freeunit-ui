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
   and no audit log. With writes enabled, anyone who reaches this interface can reconfigure
   FreeUnit, which is equivalent to code execution on the host.

If you cannot satisfy points 1 and 3, do not deploy this.

## Design decisions that follow from that

- Writes are off by default. With `FREEUNIT_UI_ENABLE_WRITES` unset, the mutating routes are
  never registered, so there is no endpoint to reach.
- The read path uses `UnitClient`, which has no write method at all. Writing needs
  `UnitWriteClient`, which only the write views construct, so a read view cannot be tricked into
  writing even when the application is configured to allow changes.
- Enabling writes requires an explicit `FREEUNIT_UI_SECRET_KEY`; the application refuses to start
  otherwise. Write forms carry a CSRF token in a `SameSite=Strict`, `HttpOnly` session cookie.
- Changes are refused if the subtree moved since the form was built, and the whole configuration
  is snapshotted before every change. Snapshots are `0600` in a `0700` directory.
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
