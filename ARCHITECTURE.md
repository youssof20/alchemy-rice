# Architecture

Alchemy separates portable domain logic from operating-system mutation.

```text
UI / CLI
    ↓
Application services
    ↓
Domain models and plans
    ↓
Reviewed setting drivers
    ↓
KDE and platform adapters
```

`src/alchemy/domain` contains immutable values that do not require KDE. `services` coordinates use cases. `drivers` owns setting-specific read, plan, apply, verify, and rollback behavior. `platform` contains process, filesystem, DBus, and Plasma-shell boundaries. `ui` and `cli` present the same underlying report.

The capability matrix is immutable for the lifetime of an inspection report, and missing evidence remains `unknown`. Windows is supported for development and unit tests, not as a simulated KDE runtime.

The transaction service acquires a single-writer lock before reading mutable state. It then creates a targeted snapshot and atomic JSON journal before mutation begins. A failed verification triggers driver-specific rollback and records whether restoration was verified. The same lifecycle supports the Phase 1 color driver and the Phase 2 registry.

Phase 2 maps icons, cursor theme and size, six font roles, Plasma theme, application style, window decoration, and selected KWin behavior to reviewed KConfig keys. Snapshot paths honor `XDG_CONFIG_HOME`. Refreshes use the session-bus notifications emitted by the corresponding upstream KCMs; cursor and Plasma themes use their official apply tools. Wallpaper state is read through Plasma's scripting DBus endpoint and written through `plasma-apply-wallpaperimage`. Wallpaper changes are limited to uniform image-plugin layouts so the previous state can be reconstructed exactly with the same public tool.

Phase 3 adds a separate panel-layout domain model rather than treating panels as generic key/value settings. Logical screen roles and percentage dimensions are resolved against Plasma's current screen geometry during planning. Slot intent is compiled into ordered widgets and expanding panel spacers. A confirmation token binds the approved plan to both the captured pre-state and resolved screen mapping.

Panel capture combines Plasma's `dumpCurrentLayoutJS` serialization with read-only scripting metadata for screen assignment, floating behavior, and pixel dimensions. The serializer intentionally omits transient applet identifiers and internal order keys. Apply creates a complete replacement set through Plasma scripting, validates installed widget types again inside the script, removes old panels only after creation succeeds, and verifies a new semantic capture. Rollback reconstructs the captured panels and widget configuration through the same API. The applet configuration file is snapshotted as a secondary recovery artifact but is not broadly overwritten.

Phase 4 adds a platform-independent rice domain. It parses hostile JSON with byte, depth, node, collection, key, string, and number limits before semantic validation. Canonicalization is owned by this domain rather than the UI or storage layer, making the same bytes and SHA-256 available on every platform. Published JSON Schemas describe the interoperable structure; built-in semantic checks cover constraints that the schema cannot express reliably.

Overrides are separate documents bound to a base ID, version, and canonical hash. Resolution uses recursive object merge semantics only within `components`, validates the complete computed document, and records leaf provenance without changing the base manifest. Compatibility evaluation consumes the immutable capability matrix and returns errors, warnings, or unknown evidence. `RiceService` coordinates read-only inspection, canonical export, integrity-checked local import, and override resolution. It does not call setting drivers or apply a rice.

Phase 5 adds a one-way creator capture service. It reads the immutable environment report and the panel driver's public inspection result, then translates only exact allowlisted KConfig sources into rice component fields. The panel translator consumes plugin identifiers and semantic geometry but never receives private widget configuration. Non-primary screen intent, custom panel lengths, and non-KDE widget provenance remain blocking review findings instead of being guessed.

Capture output passes through the rice v2 validator and a separate recursive publication sanitizer before it can be written. Findings contain JSON paths and categories, never matched values. An unsafe draft withholds both the manifest and generated summary from CLI output. Canonical export is local, refuses overwrite, and does not invoke writers, dependency installers, network clients, or upload paths.

Phase 6 adds a dependency domain and provider boundary. Resolution combines immutable rice declarations, the current capability snapshot, and versioned compatibility data. Trust is derived from reviewed source and repository classification rather than a manifest's wording. Package candidates are queried through fixed provider adapters, and missing tools or evidence remain unresolved.

An install plan is an argument vector with an explicit privilege reason and a token bound to the rice hash, environment, candidate, compatibility status, and command. Installation is a separate command that reacquires the shared mutation lock and recomputes that token before invoking the provider. Only confirmed Tier A mappings are automatable in this phase. A successful provider exit is insufficient: the adapter must observe the package afterward before an owner-only receipt is written. Dependency receipts never instruct config rollback to uninstall a package.

Phase 7 adds a gallery domain that accepts only bounded metadata projections over creator-owned,
immutable rice releases. Pull-request validation uses the trusted base revision and treats the
contributor checkout solely as input data. Remote verification derives an ownership proof URL from
the pinned repository commit, verifies canonical rice and screenshot hashes, and never invokes
repository code.

The static builder deterministically combines entries with a separate maintainer-owned metrics
document and derives all badges. `GalleryService` performs one explicit snapshot request with ETag
reuse, validates before atomically replacing the owner-only cache, and serves search, sorting, detail,
and report previews without per-entry network access. The Qt gallery reads the same cached service.

KDE-specific writers must use the highest-level tested interface available: an official `plasma-apply-*` utility, documented DBus/scripting API, a specific KConfig key with its documented refresh behavior, or a narrowly owned structured file parser. Generic code must not overwrite Plasma panel configuration.
