# Roadmap

Ordered by increasing blast radius. Nothing here is committed to a date.

## Shipped

- 0.1: status, configuration browsing, certificate expiry. Read-only.
- 0.2: opt-in configuration editing, with snapshots, conflict detection and CSRF protection.
- 0.3: configuration guidance from the bundled specification, scaffolds for new objects, and
  advisory checks before applying.
- 0.4: a change reason, verification after applying, one-click undo, and a guided editing mode
  that merges rather than replaces.

## Next: making the read-only view more useful

- Search and filter across the configuration tree
- Diff between the running configuration and a saved snapshot
- Surface access log configuration and per-listener TLS settings more legibly

## Next, on the write path

The rails that shipped cover snapshots, conflict detection and CSRF. Still missing:

1. **Automatic rollback.** A change that unitd accepts but that breaks the service is not undone
   automatically; the snapshot has to be restored by hand.
2. **A reason for each change.** Snapshots record what changed and who changed it, but not why.
3. **Structured editing for nested shapes.** The guided form covers scalar members. Objects and
   arrays — `processes`, `isolation`, route steps — still mean dropping to JSON.

Read-only remains the default and the documented safe deployment.

## Explicitly not planned

- Managing the host, packages, or anything outside FreeUnit
- Deploying application code
- A multi-tenant or multi-user permission model — use the proxy
- Wrapping `unitctl`; this talks to the API directly
