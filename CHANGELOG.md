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

### Changed

- Writing is a separate `UnitWriteClient` subclass; `UnitClient` still has no write method, so the
  read path cannot write even when writes are enabled.
- CI additionally tests Python 3.14.

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
