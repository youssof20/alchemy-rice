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

`src/alchemy/domain` contains immutable values that do not require KDE. `services` coordinates use cases. `drivers` owns knowledge about a setting and will eventually implement read, plan, apply, verify, and rollback. `platform` contains process and filesystem boundaries. `ui` and `cli` present the same underlying report.

The capability matrix is immutable for the lifetime of an inspection report, and missing evidence remains `unknown`. Windows is supported for development and unit tests, not as a simulated KDE runtime.

Phase 1 adds targeted snapshots, atomic JSON journals, a single-writer lock, plan/apply/verify/revert, and interrupted-transaction recovery around one color-scheme driver. The snapshot and journal are durable before mutation begins. A failed verification triggers rollback and records whether restoration was verified.

KDE-specific writers must use the highest-level tested interface available: an official `plasma-apply-*` utility, documented DBus/scripting API, a specific KConfig key with its documented refresh behavior, or a narrowly owned structured file parser. Generic code must not overwrite Plasma panel configuration.
