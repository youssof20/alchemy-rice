# Changelog

All notable project changes will be recorded here. The project has not made a public release.

## Unreleased

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
