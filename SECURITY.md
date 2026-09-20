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
- With writes disabled, there is no session cookie and no secret key: nothing needs signing when
  there is no CSRF token to protect.
- Configuration path segments from URLs are validated, not escaped: empty and relative segments
  are rejected before a control API path is built.
- Responses are sent with `Cache-Control: no-store`, since pages contain server configuration.

## What has been reviewed

An audit of 0.4 covered authentication coverage, CSRF, injection, secret handling, resource
limits and dependencies. Findings and their fixes:

- **HTML injection through configuration member names.** The panel listing members the bundled
  specification does not recognise joined them with markup and marked the result safe, so a
  member named `<img src=x onerror=...>` was rendered unescaped. Whoever writes the configuration
  chooses those names, so this turned config-write access into an attack on the operator's
  browser. The Content-Security-Policy would have blocked the script, but the markup still
  rendered. Fixed by escaping each name; asserted by a test.
- **No request body limit.** An upload was read into memory in full before it could be inspected.
  Bounded by `FREEUNIT_UI_MAX_UPLOAD_BYTES`, default 1 MiB.
- **Unaddressable names escaped their path segment.** `quote()` does not encode dots, so a
  certificate bundle named `..` collapsed under URL normalisation into a `PUT` at the API root
  carrying its private key. Empty and relative names are now refused by the client itself.

Checked and found sound: every mutating endpoint validates a CSRF token; `require_auth` covers
every route including static assets, with only `/healthz` exempt by design; configuration paths
reject empty and relative segments; snapshot names are matched against the listing rather than
used to build a path; reflected query parameters are escaped; security headers are present on
error responses too; the package logs nothing; snapshots never contain certificate material; and
no dependency has a known vulnerability.

## Supported versions

Pre-1.0, only the latest release receives fixes.

## Reporting a vulnerability

Use this repository's private vulnerability reporting (Security tab → *Report a vulnerability*)
rather than opening a public issue.

Include the version, the deployment shape (proxy, control socket type), and enough detail to
reproduce. Expect acknowledgement within 72 hours and an agreed disclosure timeline; the default
is coordinated disclosure once a fix is available.

Please do not test against systems you do not own.
