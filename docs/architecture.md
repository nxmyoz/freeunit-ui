# Architecture

## Layers

```
freeunit_ui/
  settings.py      environment-driven configuration
  extensions.py    the app/web seam: client factory and settings accessors
  security.py      response hardening
  app.py           application factory
  wsgi.py          the freeunit_ui.wsgi:application entry point
  unit/            control API client - knows nothing about Flask
    transport.py   builds an httpx client for a socket path or URL
    client.py      read-only and write request methods, and error mapping
    models.py      typed views of /status and /certificates
    errors.py      exception hierarchy
  schema/          FreeUnit's OpenAPI specification, vendored, and guidance built on it
    __init__.py    branch resolution and per-member description, defaults, enums
    validation.py  advisory checks against the bundled specification
    scaffolds.py   starting documents for new applications and listeners
  snapshots.py     configuration snapshots, the undo the control API lacks
  diff.py          structural comparison of two configuration documents
  references.py    what the configuration points at, and whether it is there
  pointers.py      RFC 6901 JSON Pointer construction
  web/             HTTP layer - knows nothing about sockets
    views.py       read endpoints
    writes.py      mutating endpoints, registered only when writes are enabled
    forms.py       the guided editor, merging typed input back into the document
    auth.py        identity taken from the authenticating reverse proxy
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

One test deliberately does not do this. `tests/test_integration_socket.py` runs a fake unitd on a
real UNIX socket, because a mock transport cannot prove the socket transport works.

## What is modelled and what is not

`/status` and `/certificates` have small, stable shapes, so they are pydantic models. Unknown
fields are ignored rather than rejected, so a newer FreeUnit release that adds a member does not
break an older interface; `Status.telemetry` being optional is exactly this case, as 1.36.1 added
it.

`/config` is **not** modelled. It is large, user defined, and changes every release. It is carried
as opaque JSON and rendered generically. The configuration tree is browsed by addressing members
individually (the control API exposes every subpath), rather than fetching the whole document and
walking it client side.

## Error handling

Control API failures become exceptions, and Flask error handlers turn those into pages. Since
FreeUnit 1.36.1 a rejected configuration carries an RFC 6901 JSON Pointer in `location.path` and
sometimes a `suggestion` for a near-miss member name; `UnitAPIError` keeps both, and the error
page shows them. Older servers simply omit them and the page degrades to the message alone.

## Why writes are a separate client class

`UnitClient` has no write method. `UnitWriteClient` subclasses it and adds `put_json`, and only the
write views ever construct one. A read view can hold a client all day and never find anything on
it capable of writing. Nobody has to remember not to call a method that was never there.

`create_app` takes the read and write factories separately for the same reason: it is not possible
to accidentally hand the read path something that can write.

## The bundled specification

`schema/` holds FreeUnit's OpenAPI specification, vendored as JSON so nothing needs a YAML
dependency at runtime, plus the release it came from. It answers two questions: what does this
member mean, and what does a valid starting point look like. It deliberately does not answer a
third, whether a document is valid.

That restraint is forced by drift: unitd does not serve its own specification, so this copy is
pinned to one release while the server it talks to is not. A bundled schema that confidently
refused something a newer server accepts would be worse than no schema at all. So unknown members
are reported, never removed, and nothing here can block an apply: the server's rejection, with its
JSON Pointer, remains the real answer.

`schema/validation.py` adds checks on top of that, and inherits the same restraint: a finding is
a suggestion. The apply path asks for confirmation when something looks wrong and proceeds when
the operator says so, because refusing outright would eventually refuse a correct document that a
newer server would have accepted.

One subtlety worth keeping: when a document's `type` is not one the specification knows, no branch
can be resolved and only the members common to every application are described. Member names are
then unjudgeable, so unknown-member findings are suppressed for that node; otherwise every real
member of a newer application type would be reported as unrecognised.

Scaffolds are written by hand rather than generated, because a document assembled from types alone
is valid and useless. They are checked against the schema by the test suite instead: every scaffold
must carry every member its schema marks required, so a FreeUnit release that adds one fails the
tests rather than silently producing documents the server rejects.

## Why a generated form is safe here

The usual objection to generating a form from a schema is that it becomes the only expression of
the document and silently discards whatever the schema does not cover. For a configuration format
that gains members every release, that is a guarantee of data loss.

`web/forms.py` avoids it by never replacing a document. It renders the scalar members the
specification describes, and on submit merges those values into the document as it was found:
objects, arrays and unrecognised members are copied across untouched and listed in the interface
so the operator can see the form is partial. The raw JSON editor is how those are reached, and it
is not going away.

Two consequences fall out of that. A blank field removes an optional member but never a required
one, so the form cannot construct a document it knows to be invalid. An untouched round trip is a
no-op, which the tests assert directly since it's the property the whole design rests on.

## URL namespaces

Configuration members are named by the operator, so an action word must never be a path segment
inside a configuration path (an application named `edit` would otherwise be unreachable). Editing
lives under `/edit/`, with the same URL serving the form (GET) and receiving the change (POST), and
snapshots sit at `/snapshots` rather than under `/edit`.

## Why there is no JavaScript

The Content-Security-Policy is `default-src 'none'` with no `script-src` at all, which is only
possible because nothing on any page needs script. This is a deliberate constraint, not an
oversight — CONTRIBUTING.md has the reasoning.
