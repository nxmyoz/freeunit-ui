# Deployment

> Read [SECURITY.md](../SECURITY.md) first. This interface talks to a
> root-equivalent API, and with writes enabled anyone who reaches it can reconfigure FreeUnit.

## Shape

```
browser ──mTLS──> nginx ──unix socket──> freeunit-ui (run by FreeUnit) ──> unitd control socket
```

nginx authenticates. The application asserts nothing about identity itself: it reads the header
nginx sets and, with `require_auth`, refuses anything arriving without one.

## Serving it from FreeUnit itself

FreeUnit runs Python applications natively, so it can host this interface. Understand the failure
mode before choosing it: **a configuration change that breaks listeners takes down the interface
you would use to fix it.** Snapshots are written to disk precisely so the recovery path does not
need this interface:

```console
# curl -X PUT --data-binary @/var/lib/freeunit-ui/snapshots/20260906T101500Z.json \
      --unix-socket /run/freeunit.sock http://localhost/config
```

Keep that command somewhere you can find it at 3am, or run the interface as a separate service
instead.

## Installing

```console
# install -d -o freeunit -g freeunit /opt/freeunit-ui /var/lib/freeunit-ui/snapshots
# git clone <this repository> /opt/freeunit-ui
# python -m venv /opt/freeunit-ui/.venv
# /opt/freeunit-ui/.venv/bin/pip install /opt/freeunit-ui
```

The application must run as a user allowed to open the control socket. Since FreeUnit 1.36.0 that
means root or the user unitd runs as — `freeunit` on Gentoo. Use the service account, not root.

## FreeUnit configuration

[`deploy/freeunit-ui.json`](../deploy/freeunit-ui.json) is a working starting point. Apply it into
the relevant part of your configuration rather than over the whole document.

The listener is a **UNIX socket, not a TCP port**. That is deliberate: the identity header is only
trustworthy if nothing but nginx can reach the application. Put the socket in a directory that
only nginx can traverse:

```console
# install -d -o freeunit -g nginx -m 0750 /run/freeunit-ui
```

A tmpfiles entry keeps it across reboots:

```
d /run/freeunit-ui 0750 freeunit nginx -
```

If you bind a TCP port instead, any local user can connect directly and set `X-Forwarded-User` to
whatever they like. There is no way for the application to detect that.

## nginx

[`deploy/nginx.conf`](../deploy/nginx.conf) uses client certificates. Any scheme works — OIDC via
`auth_request`, an SSO forward-auth endpoint — provided that:

1. no request reaches the application unauthenticated, and
2. `X-Forwarded-User` is **set** by nginx with `proxy_set_header`, never passed through. Because
   `proxy_set_header` replaces the incoming value, a client cannot inject its own.

## Enabling writes

Writes stay off until you decide otherwise. To enable them, add to the application's
`environment`:

```json
"FREEUNIT_UI_ENABLE_WRITES": "true",
"FREEUNIT_UI_SECRET_KEY": "<48 random bytes, urlsafe>"
```

Generate the key once and keep it stable — it signs the session cookie carrying the CSRF token,
so a value that changes per process or per restart breaks writes in confusing ways:

```console
$ python -c 'import secrets; print(secrets.token_urlsafe(48))'
```

Snapshots then appear in `FREEUNIT_UI_SNAPSHOT_DIR`, recording who made each change from the
identity nginx asserted.

## Running it outside FreeUnit

If you would rather not have the interface hosted by the server it configures:

```console
$ gunicorn --bind unix:/run/freeunit-ui/ui.sock --workers 2 freeunit_ui.wsgi:application
```

Everything else is unchanged; nginx does not care what is behind the socket.

## Checklist

- [ ] Application reachable only through nginx — UNIX socket in a directory nginx alone can traverse
- [ ] nginx authenticates every request, including static assets
- [ ] `X-Forwarded-User` set with `proxy_set_header`, not forwarded from the client
- [ ] `FREEUNIT_UI_REQUIRE_AUTH=true`, so a proxy misconfiguration fails closed
- [ ] Application runs as the unitd service account, not root
- [ ] TLS terminated at nginx
- [ ] Snapshot directory exists and is writable by that account
- [ ] The recovery `curl` command recorded somewhere outside this interface
