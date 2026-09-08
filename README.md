# Alchemy

Alchemy is a free, GPL-licensed KDE Plasma 6 ricing workbench under active development. The current Phase 4 build detects the desktop environment, provides transactional CLI paths for core appearance settings and semantic panel layouts, and safely handles the config-only `.rice` v2 format.

Every apply acquires the shared mutation lock before reading state, creates a targeted snapshot, opens a durable journal, applies through a reviewed KDE interface, verifies the observed setting, and restores the previous state if verification fails. Drivers cover color schemes, icons, cursors, fonts, Plasma themes, wallpaper, application style, window decoration, and selected KWin behavior.

The current engine targets Plasma 6.6 through 6.8, with Wayland as the primary session. Development can happen on Windows, but real KDE integration requires a Linux Plasma session.

A `.rice` is canonical declarative JSON, not an archive or installer. Alchemy validates strict component data, immutable source metadata, external dependency references, compatibility claims, and hostile-input limits without executing content from the file. Optional KDE components that contain code remain separate disclosed dependencies.

## What works now

- Read-only environment and capability detection.
- Plasma, session, distro, package-manager, portal, monitor, Nix, and login-manager observations where a reliable probe is available.
- Reviewed KConfig readers for colors, icons, cursor, fonts, application style, and window decoration.
- Text, JSON, and redacted debug output.
- A read-only Qt capability view.
- Targeted file snapshots that preserve missing files and symlinks without dereferencing them.
- Durable transaction journals and a cross-process mutation lock.
- Plan, apply, verify, revert, and interrupted-transaction recovery for reviewed core settings.
- Official KDE apply utilities for color, cursor, Plasma theme, and wallpaper changes.
- Exact KConfig keys plus the corresponding Plasma or KWin refresh signal for the remaining drivers.
- Conservative wallpaper changes that refuse non-uniform multi-desktop layouts.
- Semantic panel inspection without exposing widget configuration values.
- Declarative panel layouts with logical primary/all-screen intent, percentage sizing, and slot-based widget ordering.
- Preflight validation for every widget, explicit screen-mapping previews, and confirmation tokens that expire when the current layout or display mapping changes.
- Panel apply and exact captured-layout rollback through Plasma's scripting and serialization interfaces, without replacing the complete applet configuration file.
- Normative rice v2 and sparse-override JSON schemas with matching semantic validation.
- Deterministic canonical JSON serialization and SHA-256 verification.
- Safe rice inspect, export, local import, and base-plus-override resolution without desktop mutation.
- Compatibility evaluation that preserves unknown evidence and distinguishes warnings from hard failures.
- Unit tests that run without a KDE session.

The inspector reports unknown values instead of inferring KDE support from a version number. Union detection is deliberately unknown until a stable capability probe is available.

## Run from source

Alchemy requires Python 3.12 or newer.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'

alchemy inspect
alchemy inspect --json
alchemy debug-info
alchemy gui
alchemy plan-color BreezeDark
alchemy apply-color BreezeDark --yes
alchemy list-settings
alchemy plan-setting icons.theme Papirus-Dark
alchemy apply-setting icons.theme Papirus-Dark --yes
alchemy plan-setting wallpaper.image /home/me/Pictures/wallpaper.png
alchemy inspect-panels
alchemy plan-panels examples/panel-layout.json
alchemy apply-panels examples/panel-layout.json --plan-token TOKEN_FROM_PLAN --yes
alchemy rice-export examples/rice-v2-draft.json night-workbench.rice
alchemy rice-inspect night-workbench.rice
alchemy rice-resolve night-workbench.rice examples/rice-override.json
alchemy rice-import night-workbench.rice --sha256 EXPECTED_HASH
alchemy revert --last
alchemy recovery --list
```

Run the test suite with:

```bash
pytest
```

The repository does not yet provide a distro package or portable release. See [PACKAGING.md](PACKAGING.md) for the current status.

## Safety boundary

Writers are unavailable unless the host is Linux, an active KDE session reports a version in the current 6.6-6.8 target window, plasma-manager is not detected as the state owner, and each driver's required KDE tools exist. External commands are invoked as argument vectors without a shell. Debug output is generated locally and redacted before display; Alchemy does not upload it.

The transaction and driver behavior has fake-boundary unit coverage but has not yet been validated in a real Plasma VM. Current limitations and test evidence are recorded in [COMPATIBILITY.md](COMPATIBILITY.md). Setting names and accepted values are documented in [SETTING_REFERENCE.md](SETTING_REFERENCE.md); panel layout fields are documented in [PANEL_LAYOUT.md](PANEL_LAYOUT.md).

## Project documents

- [ARCHITECTURE.md](ARCHITECTURE.md)
- [SECURITY.md](SECURITY.md)
- [PRIVACY.md](PRIVACY.md)
- [CONTRIBUTING.md](CONTRIBUTING.md)
- [RICE_FORMAT.md](RICE_FORMAT.md)
- [SETTING_REFERENCE.md](SETTING_REFERENCE.md)
- [PANEL_LAYOUT.md](PANEL_LAYOUT.md)
- [COMPATIBILITY.md](COMPATIBILITY.md)
- [PACKAGING.md](PACKAGING.md)
- [CHANGELOG.md](CHANGELOG.md)

No real apply/revert recording exists yet. A real Plasma recording will replace this note after the implemented drivers pass KDE integration testing.
