# Architecture

## Layers

```
freeunit_ui/
  settings.py      environment-driven configuration
  extensions.py    the app/web seam: client factory and settings accessors
  security.py      response hardening
  app.py           application factory
  unit/            control API client - knows nothing about Flask
    transport.py   builds an httpx client for a socket path or URL
    client.py      read-only request methods and error mapping
    models.py      typed views of /status and /certificates
    errors.py      exception hierarchy
  web/             HTTP layer - knows nothing about sockets
    views.py       endpoints
    paths.py       validation of user supplied config paths
    templates/, static/
```

The dependency direction is one way: `web` depends on `unit`, never the reverse. `extensions.py`
exists so the web layer can reach the client factory without importing the application factory,
which would be a cycle.

## Why the client is injected

`UnitClient` takes an already built `httpx.Client`. That single decision is what makes the whole
suite runnable without a FreeUnit instance: tests pass an `httpx.MockTransport` and drive real
client code against canned payloads. `create_app` accepts a `client_factory` for the same reason.

One test deliberately does not do this — `tests/test_integration_socket.py` runs a fake unitd on a
real UNIX socket, because a mock transport cannot prove the socket transport works.

## What is modelled and what is not

`/status` and `/certificates` have small, stable shapes, so they are pydantic models. Unknown
fields are ignored rather than rejected, so a newer FreeUnit release that adds a member does not
break an older interface; `Status.telemetry` being optional is exactly this case, as 1.36.1 added
it.

`/config` is **not** modelled. It is large, user defined, and changes every release. It is carried
as opaque JSON and rendered generically. The configuration tree is browsed by addressing members
individually — the control API exposes every subpath — rather than fetching the whole document
and walking it client side.

## Error handling

Control API failures become exceptions, and Flask error handlers turn those into pages. Since
FreeUnit 1.36.1 a rejected configuration carries an RFC 6901 JSON Pointer in `location.path` and
sometimes a `suggestion` for a near-miss member name; `UnitAPIError` keeps both, and the error
page shows them. Older servers simply omit them and the page degrades to the message alone.

## Why there is no JavaScript

The Content-Security-Policy is `default-src 'none'` with no `script-src` at all, which is only
possible because nothing on any page needs script. This is a deliberate constraint, not an
oversight — see CONTRIBUTING.md.
