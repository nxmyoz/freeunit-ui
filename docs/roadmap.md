# Roadmap

Ordered by increasing blast radius. Nothing here is committed to a date.

## Now: read-only (0.1)

Status, configuration browsing, certificate expiry.

## Next: making the read-only view more useful

- Search and filter across the configuration tree
- Diff between the running configuration and a saved snapshot
- Surface access log configuration and per-listener TLS settings more legibly

## Later: guarded editing

Writes are the point at which this becomes dangerous, so they arrive with their safety rails, not
before them:

1. **Snapshots first.** Store `GET /config` before every change, with one-click restore. The
   control API has no versioning of its own; this has to exist before any write path does.
2. **Optimistic locking.** The API exposes no `ETag`, so two operators editing concurrently will
   silently clobber each other. Hash the document on load and refuse to apply against a changed
   server state.
3. **Validation before apply.** There is no dry-run endpoint. Client-side validation against the
   OpenAPI schema, then apply, then verify — with rollback on failure.
4. **Narrow scope.** Listeners and routes first. Applications last, since `executable` and `user`
   are the members that make this a code execution interface.

Editing will stay opt-in via configuration, and the read-only deployment will remain supported and
documented as the safe default.

## Explicitly not planned

- Managing the host, packages, or anything outside FreeUnit
- Deploying application code
- A multi-tenant or multi-user permission model — use the proxy
- Wrapping `unitctl`; this talks to the API directly
