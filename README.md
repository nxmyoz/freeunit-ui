# FreeUnit UI

A web interface for the [FreeUnit](https://github.com/freeunitorg/freeunit) control API —
the community LTS fork of NGINX Unit.

Unit is configured entirely through a JSON REST API rather than config files, which makes it
excellent to automate and awkward to inspect. Every "nginx GUI" project targets classic nginx
config files and none of them speak this API. FreeUnit UI reads it directly and renders it:
runtime status, the configuration tree, and certificate expiry.

**This release is read-only.** It issues nothing but `GET` requests.

## Read this before you install it

Writing FreeUnit configuration is equivalent to root. A configuration document can define an
application with an arbitrary `executable` and `user`, so anything able to write config can run
arbitrary code. Even read access exposes your full server configuration, including which
certificates and applications exist.

Consequently:

- **This interface ships no authentication.** Put it behind something that has it — a reverse
  proxy with client certificates, OIDC, or an SSO forward-auth endpoint.
- **It binds to `127.0.0.1` by default.** Do not expose it directly to a network.
- Since FreeUnit 1.36.0 the UNIX control socket only accepts peers whose effective UID is root
  or the user unitd runs as, so this process must run as one of them. A compromise of this
  interface is therefore a compromise of unitd. Treat it as privileged software.

Being read-only is a deliberate part of that posture: an interface that cannot write cannot be
tricked into writing.

## Requirements

- Python 3.11 or newer
- FreeUnit or NGINX Unit with a reachable control socket
- FreeUnit 1.36.1 or newer to get JSON Pointer error locations (older releases work, with
  less precise error reporting)

## Quick start

```console
$ git clone <this repository> && cd freeunit-ui
$ python -m venv .venv && . .venv/bin/activate
$ pip install -e .
$ FREEUNIT_UI_CONTROL=/run/freeunit.sock freeunit-ui
```

Not released anywhere yet, so there is no `pip install freeunit-ui`.

Then open <http://127.0.0.1:8099/>.

`freeunit-ui` runs Flask's development server, which is fine for a look around and not for
anything else. For real deployments see [docs/deployment.md](docs/deployment.md).

## Configuration

Every setting is an environment variable prefixed `FREEUNIT_UI_`.

| Variable | Default | Meaning |
| --- | --- | --- |
| `FREEUNIT_UI_CONTROL` | `/run/freeunit.sock` | Control socket path, or an `http://` URL for a TCP control socket |
| `FREEUNIT_UI_HOST` | `127.0.0.1` | Development server bind address |
| `FREEUNIT_UI_PORT` | `8099` | Development server port |
| `FREEUNIT_UI_TIMEOUT` | `10.0` | Control API request timeout, seconds |
| `FREEUNIT_UI_CERT_EXPIRY_WARNING_DAYS` | `30` | Highlight certificates expiring within this window |

Distributions differ on the socket path: Gentoo's `www-servers/freeunit` uses
`/run/freeunit.sock`, upstream packages commonly use `/var/run/control.unit.sock`.

## Scope

In scope: reading and presenting what the control API exposes, and making expiry, misconfiguration
and runtime health legible.

Out of scope: being a PaaS, deploying applications, managing the host, or wrapping
`unitctl`. Guarded configuration editing with snapshots and rollback is planned — see
[docs/roadmap.md](docs/roadmap.md) — but it will stay opt-in and auditable.

## Documentation

- [Architecture](docs/architecture.md) — how the pieces fit together and why
- [Deployment](docs/deployment.md) — running it safely
- [Security model](SECURITY.md) — trust boundaries and how to report a vulnerability
- [Contributing](CONTRIBUTING.md) — development setup and expectations

## License

Apache License 2.0 — see [LICENSE](LICENSE). The same license FreeUnit itself uses.
