# FreeUnit UI

A web interface for the [FreeUnit](https://github.com/freeunitorg/freeunit) control API —
the community LTS fork of NGINX Unit.

Unit is configured entirely through a JSON REST API rather than config files, which makes it
excellent to automate and awkward to inspect. Every "nginx GUI" project targets classic nginx
config files and none of them speak this API. FreeUnit UI reads it directly and renders it:
runtime status, the configuration tree, and certificate expiry.

**It is read-only by default.** Configuration editing exists but must be turned on deliberately, and brings snapshots, conflict detection and CSRF protection with it.

## Read this before you install it

Writing FreeUnit configuration is equivalent to root. A configuration document can define an
application with an arbitrary `executable` and `user`, so anything able to write config can run
arbitrary code. Even read access exposes your full server configuration, including which
certificates and applications exist.

Consequently:

- **This interface authenticates nobody.** Put it behind something that does — a reverse proxy
  with client certificates, OIDC, or an SSO forward-auth endpoint. It can read the identity that
  proxy asserts, show it, record it against configuration changes, and refuse requests that
  arrive without one, but the proxy is what decides who gets in.
- **It binds to `127.0.0.1` by default.** Do not expose it directly to a network.
- Since FreeUnit 1.36.0 the UNIX control socket only accepts peers whose effective UID is root
  or the user unitd runs as, so this process must run as one of them. A compromise of this
  interface is therefore a compromise of unitd. Treat it as privileged software.

Read-only is the default for that reason. When writes are off, the mutating routes are not
registered at all — there is no endpoint to reach rather than an endpoint that declines — and the
read path uses a client class that has no write method on it.

## Requirements

- Python 3.11 or newer
- FreeUnit or NGINX Unit with a reachable control socket
- FreeUnit 1.36.1 or newer to get JSON Pointer error locations (older releases work, with
  less precise error reporting)

## Quick start

```console
$ git clone ssh://git@git.dtsi.eu:4242/dtsi/freeunit-ui.git && cd freeunit-ui
$ python -m venv .venv && . .venv/bin/activate
$ pip install -e .
$ FREEUNIT_UI_CONTROL=/run/freeunit.sock freeunit-ui
```

Not published yet, so there is no `pip install freeunit-ui`.

Then open <http://127.0.0.1:8099/>.

`freeunit-ui` runs Flask's development server, which is fine for a look around and not for
anything else. For real deployments see [docs/deployment.md](docs/deployment.md).

## Looking at it first

No FreeUnit needed:

```console
$ python tools/demo.py --writes --user alice@example.org
```

This runs the interface against a fake control API with realistic data, on
<http://127.0.0.1:8099/>.

## Configuration

Every setting is an environment variable prefixed `FREEUNIT_UI_`.

| Variable | Default | Meaning |
| --- | --- | --- |
| `FREEUNIT_UI_CONTROL` | `/run/freeunit.sock` | Control socket path, or an `http://` URL for a TCP control socket |
| `FREEUNIT_UI_HOST` | `127.0.0.1` | Development server bind address |
| `FREEUNIT_UI_PORT` | `8099` | Development server port |
| `FREEUNIT_UI_TIMEOUT` | `10.0` | Control API request timeout, seconds |
| `FREEUNIT_UI_CERT_EXPIRY_WARNING_DAYS` | `30` | Highlight certificates expiring within this window |
| `FREEUNIT_UI_MAX_RENDER_CHARS` | `512000` | Truncate a rendered configuration document beyond this size |
| `FREEUNIT_UI_AUTH_HEADER` | — | Header the proxy sets with the operator's identity, e.g. `X-Forwarded-User` |
| `FREEUNIT_UI_REQUIRE_AUTH` | `false` | Refuse requests arriving without that identity |
| `FREEUNIT_UI_ENABLE_WRITES` | `false` | Allow configuration changes. Read the section below first |
| `FREEUNIT_UI_SECRET_KEY` | — | Session signing key. Required when writes are enabled |
| `FREEUNIT_UI_SESSION_COOKIE_SECURE` | `true` | Mark the session cookie Secure; turn off only for plain-HTTP loopback testing |
| `FREEUNIT_UI_SNAPSHOT_DIR` | `/var/lib/freeunit-ui/snapshots` | Where configuration is saved before each change |
| `FREEUNIT_UI_SNAPSHOT_KEEP` | `50` | Snapshots retained before pruning |

Distributions differ on the socket path: Gentoo's `www-servers/freeunit` uses
`/run/freeunit.sock`, upstream packages commonly use `/var/run/control.unit.sock`.

## Beyond the configuration

**References** shows what listeners and routes point at and whether it is configured — the class
of mistake a schema cannot catch, since it lives in the document. Destinations built from
variables are reported as decided-per-request rather than broken.

**Snapshots** can be compared with the running configuration or with each other, so a change is
readable rather than merely reversible.

**Applications** can be restarted from the overview. That is not a configuration change: nothing
is stored and no snapshot is taken.

**Certificate bundles** can be uploaded, by file or paste, replacing an existing bundle under the
same name. Listeners referring to it pick up the new certificate with no configuration change. Key
material is never written to a snapshot and never echoed back into the form.

## Two ways to configure

**Guided** renders the members the specification describes as typed inputs — text, numbers,
true/false, and a menu where the value must be one of a set. **Edit as JSON** remains, and is how
you reach everything else. The two modes link to each other from every configuration page.

The guided form **never replaces a document, it merges into it**. Objects, arrays and members the
bundled specification has never heard of are carried across untouched, and the form names them so
you can see it is not the whole picture. That is what makes a schema-driven form safe here: a form
that replaced the document would quietly delete configuration it did not understand, which for a
format that grows every release is a matter of when, not if.

A blank field removes an optional member. Required members are never removed, so the form cannot
produce a document it knows to be invalid.

## Configuration guidance

FreeUnit publishes an OpenAPI specification describing its configuration, and a copy is bundled
here. Browsing the configuration shows what each member means, which are required, their defaults
and their permitted values — chosen for the right application type, since a Python application and
a PHP one have different shapes. Creating a listener or an application offers a starting point with
the required members already present.

Editing also checks the document before it is sent: missing required members, values outside a
permitted set, members of the wrong type, and names the specification does not recognise — each
reported at a JSON Pointer, the way unitd reports its own errors. A typo like `modul` shows up
twice, as a missing `module` and an unrecognised `modul`, which is exactly the signal you want.

Findings **warn and ask**; they never refuse. You get an *Apply anyway* button, and a *Check*
button to look before applying.

It is **guidance, never a gate**. unitd does not serve its own specification, so the bundled copy
is pinned to one release and will drift from your server: a newer FreeUnit will accept members it
has never heard of. Nothing here refuses a configuration, unknown members are reported rather than
removed, and your server remains the only authority on what is valid. Re-vendor it on a bump with
`python tools/vendor_spec.py <version>`.

## Enabling configuration editing

```console
$ export FREEUNIT_UI_ENABLE_WRITES=true
$ export FREEUNIT_UI_SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')"
```

The interface refuses to start with writes enabled and no key, rather than generating one — a
generated key would appear to work and then silently break CSRF protection across workers and
restarts.

With writes on you get an **Edit** action on any configuration subtree and a **Snapshots** page.
Every change goes through the same sequence:

1. the CSRF token is checked,
2. the subtree is re-read and compared with what the form was built from, so two operators cannot
   silently overwrite each other — the control API offers no `ETag`,
3. the whole configuration is snapshotted, because the API has no undo,
4. the change is applied, and if unitd refuses it the error page shows the JSON Pointer and typo
   suggestion it reported.

Snapshots are written `0600` in a `0700` directory and contain the complete configuration.
Restoring one snapshots the current state first, so a restore is itself reversible.

## Scope

In scope: reading and presenting what the control API exposes, making expiry, misconfiguration
and runtime health legible, and editing configuration safely for operators who opt in.

Out of scope: being a PaaS, deploying applications, managing the host, or wrapping `unitctl`.

## Deploying

The supported shape is FreeUnit serving this interface on a UNIX socket, with nginx in front doing
the authentication:

```
browser ──mTLS──> nginx ──unix socket──> freeunit-ui (run by FreeUnit) ──> unitd control socket
```

Working configuration for both sides is in [`deploy/`](deploy/), and
[docs/deployment.md](docs/deployment.md) walks through it — including why the listener is a UNIX
socket rather than a port, and the failure mode of letting the server host the interface that
configures it.

## Documentation

- [Architecture](docs/architecture.md) — how the pieces fit together and why
- [Deployment](docs/deployment.md) — running it safely
- [Security model](SECURITY.md) — trust boundaries and how to report a vulnerability
- [Contributing](CONTRIBUTING.md) — development setup and expectations

## License

Apache License 2.0 — see [LICENSE](LICENSE). The same license FreeUnit itself uses.
