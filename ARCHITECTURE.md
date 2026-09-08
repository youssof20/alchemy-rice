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

KDE-specific writers must use the highest-level tested interface available: an official `plasma-apply-*` utility, documented DBus/scripting API, a specific KConfig key with its documented refresh behavior, or a narrowly owned structured file parser. Generic code must not overwrite Plasma panel configuration.
