# Roadmap

Ordered by increasing blast radius. Nothing here is committed to a date.

## Shipped

- 0.1: status, configuration browsing, certificate expiry. Read-only.
- 0.2: opt-in configuration editing, with snapshots, conflict detection and CSRF protection.
- 0.3: configuration guidance from the bundled specification, and scaffolds for new objects.

## Next: making the read-only view more useful

- Search and filter across the configuration tree
- Diff between the running configuration and a saved snapshot
- Surface access log configuration and per-listener TLS settings more legibly

## Next, on the write path

The rails that shipped cover snapshots, conflict detection and CSRF. Still missing:

1. **Advisory validation before apply.** The schema is now bundled, so required members and
   unknown names could be checked at the form. It must warn rather than block, for the drift
   reason above.
2. **Automatic rollback.** A change that unitd accepts but that breaks the service is not undone
   automatically; the snapshot has to be restored by hand.
3. **An audit trail.** Snapshots record what the configuration was, not who changed it or why.
4. **Structured editing.** Editing raw JSON in a textarea is honest but unhelpful for listeners
   and routes, which have a small, well known shape.

Read-only remains the default and the documented safe deployment.

## Explicitly not planned

- Managing the host, packages, or anything outside FreeUnit
- Deploying application code
- A multi-tenant or multi-user permission model — use the proxy
- Wrapping `unitctl`; this talks to the API directly
