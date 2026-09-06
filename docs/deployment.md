# Deployment

> Read [SECURITY.md](../SECURITY.md) first. This interface has no authentication and talks to a
> root-equivalent API.

## The shape to aim for

```
browser ──TLS──> reverse proxy (authenticates) ──> freeunit-ui (loopback) ──> unitd control socket
```

The proxy is not optional. It is where authentication, TLS and rate limiting live.

## Running it

`freeunit-ui` starts Flask's development server: single threaded, no hardening. Use it to look
around, not to deploy. For a real deployment run the WSGI application under a production server:

```console
$ gunicorn --bind 127.0.0.1:8099 --workers 2 'freeunit_ui.app:create_app()'
```

The process must be able to open the control socket. Since FreeUnit 1.36.0 that means running as
root or as the user unitd runs as — on Gentoo, `freeunit`:

```
command_user="freeunit:freeunit"
```

Prefer the service account over root. It is the smaller blast radius, and it is sufficient.

## Serving it from FreeUnit itself

Tempting, since FreeUnit runs Python applications natively. Be aware of the failure mode: a
configuration change that breaks listeners also takes down the interface you would use to fix it.
Keep `unitctl` or `curl` against the control socket as an escape hatch, or run the interface as a
separate service.

## Example: nginx with forward authentication

```nginx
location / {
    auth_request /_auth;
    proxy_pass http://127.0.0.1:8099;
    proxy_set_header Host $host;
}
```

Any equivalent works — client certificates, OIDC, or an SSO forward-auth endpoint. What matters is
that unauthenticated requests never reach the application.

## Checklist

- [ ] Bound to loopback, or to a network only the proxy can reach
- [ ] Proxy authenticates every request, including static assets
- [ ] Process runs as the unitd service account, not root, where possible
- [ ] TLS terminated at the proxy
- [ ] Access to the proxy restricted to operators
