# Contributing

Thanks for considering a contribution.

## Ground rules

This is privileged software — see [SECURITY.md](SECURITY.md). Two rules follow from that and are
not negotiable in review:

1. **No JavaScript.** The Content-Security-Policy forbids scripts entirely. Adding one inline
   handler silently weakens the whole policy.
2. **Write paths keep their rails.** Anything issuing a non-`GET` request must go through
   `UnitWriteClient`, be registered only when `enable_writes` is set, verify the CSRF token,
   check the baseline digest, and snapshot before applying. Do not add a mutating route that
   skips one of those, and do not put write methods on `UnitClient`.

## Development setup

```console
$ python -m venv .venv && . .venv/bin/activate
$ pip install -e '.[dev]'
$ pre-commit install && pre-commit install --hook-type pre-push
$ pytest
```

The hooks run formatting, linting and type checking on every commit, and the
test suite on push.

## Before opening a pull request

```console
$ ruff format .
$ ruff check .
$ mypy
$ pytest
```

All four must pass. Coverage is enforced at 90%.

## Looking at it without a FreeUnit instance

```console
$ python tools/demo.py --writes --user alice@example.org
```

That serves canned but realistic control API responses over a temporary UNIX socket and runs the
interface against them on <http://127.0.0.1:8099/>. The fixture deliberately includes a
certificate expiring soon and one already expired, failing telemetry spans, and applications in
three languages, so the states worth designing for are all visible. `--user` stands in for the
reverse proxy asserting an identity. Nothing under `tools/` is part of the installed package.

## Testing without a FreeUnit instance

The control API client takes an injected `httpx.Client`, so tests drive it with
`httpx.MockTransport`. See `tests/conftest.py` for the canned payloads. You do not need a running
unitd to work on this.

If you are adding support for a field that a newer FreeUnit release introduced, add it to the
canned payload and assert both that it is read and that its absence is tolerated — the models
ignore unknown fields on purpose so that a newer server does not break an older interface.

## Commit messages

One logical change per commit. Explain *why* in the body; the diff already shows what. If a
change is driven by upstream behaviour, cite the release that changed it.

## Code of conduct

This project follows the [Contributor Covenant](CODE_OF_CONDUCT.md).
