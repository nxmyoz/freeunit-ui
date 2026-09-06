# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

