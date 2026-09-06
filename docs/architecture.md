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
  snapshots.py     configuration snapshots, the undo the control API lacks
  web/             HTTP layer - knows nothing about sockets
    views.py       read endpoints
    writes.py      mutating endpoints, registered only when writes are enabled
    csrf.py        token issue and validation for the write forms
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

## Why writes are a separate client class

`UnitClient` has no write method. `UnitWriteClient` subclasses it and adds `put_json` and
`delete_path`, and only the write views ever construct one. So a read view holding a client has
nothing to call, by construction rather than by discipline — which is what makes "read-only by
default" a property of the code and not just of a flag.

`create_app` takes the read and write factories separately for the same reason: it is not possible
to accidentally hand the read path something that can write.

## URL namespaces

Configuration members are named by the operator, so an action word must never be a path segment
inside a configuration path — an application named `edit` would otherwise be unreachable. Editing
lives under `/edit/`, with the same URL serving the form (GET) and receiving the change (POST), and
snapshots sit at `/snapshots` rather than under `/edit`.

## Why there is no JavaScript

The Content-Security-Policy is `default-src 'none'` with no `script-src` at all, which is only
possible because nothing on any page needs script. This is a deliberate constraint, not an
oversight — see CONTRIBUTING.md.
