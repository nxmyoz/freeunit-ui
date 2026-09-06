# Contributing

Thanks for considering a contribution.

## Ground rules

This is privileged software — see [SECURITY.md](SECURITY.md). Two rules follow from that and are
not negotiable in review:

1. **No JavaScript.** The Content-Security-Policy forbids scripts entirely. Adding one inline
   handler silently weakens the whole policy.
2. **No write paths without a design discussion first.** Please open an issue before implementing
   anything that issues a non-`GET` request to the control API.

## Development setup

```console
$ python -m venv .venv && . .venv/bin/activate
$ pip install -e '.[dev]'
$ pytest
```

## Before opening a pull request

```console
$ ruff format .
$ ruff check .
$ mypy
$ pytest
```

All four must pass. Coverage is enforced at 90%.

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
