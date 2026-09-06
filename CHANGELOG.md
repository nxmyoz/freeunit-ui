# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Opt-in configuration editing behind `FREEUNIT_UI_ENABLE_WRITES`, off by default. When off the
  mutating routes are not registered at all.
- Configuration snapshots, taken automatically before every change and before every restore, with
  a page to review and restore them. Written `0600` in a `0700` directory.
- Conflict detection: a change is refused if the subtree moved since the form was built, since the
  control API offers no `ETag`.
- CSRF protection on every write form, in a `SameSite=Strict`, `HttpOnly` session cookie. Enabling
  writes requires an explicit `FREEUNIT_UI_SECRET_KEY` and refuses to start without one.
- `/healthz` liveness endpoint that deliberately does not touch the control socket.
- Truncation of oversized configuration documents, bounded by `FREEUNIT_UI_MAX_RENDER_CHARS`.
- `py.typed`, so the package's annotations are visible to consumers.
- pre-commit hooks: formatting, linting and typing per commit, tests on push, plus private-key
  detection.

- Identity from a reverse proxy via `FREEUNIT_UI_AUTH_HEADER`, shown in the interface and
  recorded against every snapshot, with `FREEUNIT_UI_REQUIRE_AUTH` to refuse requests that arrive
  without one.
- `freeunit_ui.wsgi:application` entry point, and `deploy/` with working FreeUnit and nginx
  configuration for running the interface under FreeUnit behind nginx.

- `tools/demo.py`, which runs the interface against a fake control API so it can be looked at
  and worked on without a FreeUnit instance.

- Configuration guidance from FreeUnit's OpenAPI specification, vendored into the package:
  member descriptions, required members, defaults and permitted values while browsing, resolved
  against the right branch for an application's `type`.
- Scaffolds for new applications and listeners, offered when editing a path that does not exist
  yet, which now creates it rather than failing to load.
- `tools/vendor_spec.py` to re-vendor the specification on a FreeUnit bump.

- Advisory checks before applying a configuration: missing required members, values outside an
  enum, wrong types (including inside nested objects), and unrecognised member names, each at a
  JSON Pointer. Findings warn and ask for confirmation rather than refusing, and a Check button
  reports without applying.

- A reason recorded with every change, shown on the snapshots page, so snapshots say why as well
  as what and who.
- Verification after applying: the subtree is read back and the result reported when what unitd
  stored differs from what was sent.
- A one-click undo on the page you land on after a change, restoring the snapshot taken
  immediately before it.

- A guided editing mode rendering described members as typed inputs, alongside the raw JSON
  editor, which remains. The form merges into the stored document rather than replacing it, so
  objects, arrays and members the specification does not describe survive untouched and are named
  in the interface.

### Changed

- Writing is a separate `UnitWriteClient` subclass; `UnitClient` still has no write method, so the
  read path cannot write even when writes are enabled.
- CI additionally tests Python 3.14.
- Snapshots keep their metadata in a sibling `.meta.json`, so the snapshot file itself stays a
  plain configuration document usable with `curl` or `unitctl`.

## [0.1.0] - 2026-09-06

Initial release. Read-only throughout.

### Added

- Overview page with connection and request counters, per-application process counts, and
  OpenTelemetry span export health where FreeUnit 1.36.1 or newer reports it.
- Browsable configuration tree backed by the control API, addressing members individually
  rather than fetching the whole document for every view.
- Certificate listing with parsed expiry and a configurable warning window.
- Error pages that surface the RFC 6901 JSON Pointer and typo suggestion that FreeUnit 1.36.1
  added to configuration validation failures.
- Hardened responses: `default-src 'none'` with no script allowance, `no-store`, and the usual
  framing and sniffing protections.
