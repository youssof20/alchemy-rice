# Changelog

All notable project changes will be recorded here. The project has not made a public release.

## Unreleased

### Phase 4 — rice v2

- Added normative JSON Schemas for config-only rice v2 manifests and hash-bound sparse overrides.
- Added duplicate-key rejection and bounded hostile-input parsing.
- Added deterministic UTF-8 canonical JSON serialization and SHA-256 verification.
- Added strict semantic validation for metadata, compatibility ranges, components, panels, external dependency references, licenses, and gallery media references.
- Added base-plus-override resolution limited to component state, with final validation and leaf provenance.
- Added capability-driven compatibility reports with compatible, warning, incompatible, and unknown states.
- Added CLI workflows for canonical export, inspection, local integrity-checked import, and override resolution; none apply desktop state.
- Added format examples and unit coverage for canonicalization, malformed input, impossible ranges, hash mismatch, cache tampering, compatibility, and override binding.

### Phase 3 — semantic panel engine

- Added strict declarative panel-layout parsing with input caps, semantic dimensions, logical screen roles, and duplicate-edge refusal.
- Added public current-panel inspection using Plasma's layout serializer and scripting metadata.
- Added left/center/right widget-slot compilation with expanding Plasma spacers and stable ordering.
- Added installed-widget preflight validation with explicit refusal for missing third-party dependencies.
- Added complete multi-monitor mapping previews and confirmation tokens invalidated by layout or display changes.
- Added Plasma-scripted panel replacement, semantic verification, captured configuration rollback, and transaction recovery support without broad applet configuration replacement.
- Redacted transaction internals from CLI output and restricted journal and snapshot permissions on POSIX systems.
- Added fake-boundary coverage for parser limits, mapping, dependencies, apply, verification, and automatic rollback.

### Phase 2 — core Plasma drivers

- Added a registry of transactional drivers for icons, cursors, fonts, Plasma theme, application style, window decoration, and selected KWin settings.
- Added KDE session-bus refresh adapters for palette, font, style, icon, cursor, and KWin configuration changes.
- Added a wallpaper driver using Plasma's scripting query and official apply utility, with exact uniform-layout rollback and conservative multi-desktop refusal.
- Generalized snapshot, journal, verification, rollback, revert, and recovery handling across setting drivers.
- Added generic setting discovery, plan, and confirmed apply commands.
- Added fake-boundary tests for KConfig commands, refresh actions, validation, wallpaper safety, and cross-driver transactions.

### Phase 1 — transaction foundation

- Added targeted snapshot capture and restore with hashes and symlink metadata.
- Added atomically persisted transaction journals and state-transition validation.
- Added a shared mutation lock with conservative stale-lock recovery.
- Added color-scheme plan, apply, verification, automatic rollback, and explicit revert.
- Added incomplete-journal discovery and rollback recovery.
- Added tests for snapshot boundaries, locks, journals, failures, revert, and restart recovery.

### Phase 0 — read-only inspector

- Added immutable environment and capability reports.
- Added conservative detection for Plasma, session, distro, package tools, portals, monitors, login manager, immutable hosts, Nix, and plasma-manager.
- Added reviewed read-only KConfig setting readers.
- Added text, JSON, and redacted debug output.
- Added a read-only Qt capability window.
- Added unit tests that do not require KDE or Qt.
- Added public architecture, security, privacy, compatibility, packaging, and contribution documentation.
