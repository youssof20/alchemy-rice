# Alchemy

Alchemy is a free, GPL-licensed KDE Plasma 6 ricing workbench under active development. The current Phase 1 build detects the desktop environment, reads a small reviewed set of KDE appearance settings, and provides a transactional CLI path for one color-scheme change.

Color-scheme apply creates a targeted snapshot, opens a durable journal, acquires the shared mutation lock, applies through KDE's color-scheme tool, verifies the observed setting, and restores the previous scheme if verification fails. Other settings remain read-only.

Target support is Plasma 6.6 and newer, with Wayland as the primary session. Development can happen on Windows, but real KDE integration requires a Linux Plasma session.

A future `.rice` file will be declarative JSON. Alchemy will not execute code contained in a rice. Optional KDE components that contain code will be handled separately as disclosed dependencies with source and trust information.

## What works now

- Read-only environment and capability detection.
- Plasma, session, distro, package-manager, portal, monitor, Nix, and login-manager observations where a reliable probe is available.
- Reviewed KConfig readers for colors, icons, cursor, fonts, application style, and window decoration.
- Text, JSON, and redacted debug output.
- A read-only Qt capability view.
- Targeted file snapshots that preserve missing files and symlinks without dereferencing them.
- Durable transaction journals and a cross-process mutation lock.
- Color-scheme plan, apply, verify, revert, and interrupted-transaction recovery commands.
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
alchemy revert --last
alchemy recovery --list
```

Run the test suite with:

```bash
pytest
```

The repository does not yet provide a distro package or portable release. See [PACKAGING.md](PACKAGING.md) for the current status.

## Safety boundary

Only the color-scheme driver can write settings. It is unavailable unless the host is Linux, Plasma reports a version in the current 6.6-6.8 target window, and the required KDE read/apply tools exist. External commands are invoked as argument vectors without a shell. Debug output is generated locally and redacted before display; Alchemy does not upload it.

The transaction foundation has unit coverage but has not yet been validated in a real Plasma VM. Current limitations and test evidence are recorded in [COMPATIBILITY.md](COMPATIBILITY.md).

## Project documents

- [ARCHITECTURE.md](ARCHITECTURE.md)
- [SECURITY.md](SECURITY.md)
- [PRIVACY.md](PRIVACY.md)
- [CONTRIBUTING.md](CONTRIBUTING.md)
- [RICE_FORMAT.md](RICE_FORMAT.md)
- [COMPATIBILITY.md](COMPATIBILITY.md)
- [PACKAGING.md](PACKAGING.md)
- [CHANGELOG.md](CHANGELOG.md)

No real apply/revert recording exists yet because that workflow has not been implemented. A real Plasma recording will replace this note after it passes KDE integration testing.
