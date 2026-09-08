# Alchemy

Alchemy is a free, GPL-licensed KDE Plasma 6 ricing workbench under active development. The current Phase 0 build is a **read-only inspector**: it detects the desktop environment and reads a small reviewed set of KDE appearance settings. It cannot apply or revert a rice yet.

The target workflow is inspect, preview, plan, snapshot, apply, verify, and revert. Apply will remain disabled until the snapshot, durable journal, single-writer lock, verification, and recovery path are implemented and tested.

Target support is Plasma 6.6 and newer, with Wayland as the primary session. Development can happen on Windows, but real KDE integration requires a Linux Plasma session.

A future `.rice` file will be declarative JSON. Alchemy will not execute code contained in a rice. Optional KDE components that contain code will be handled separately as disclosed dependencies with source and trust information.

## What works now

- Read-only environment and capability detection.
- Plasma, session, distro, package-manager, portal, monitor, Nix, and login-manager observations where a reliable probe is available.
- Reviewed KConfig readers for colors, icons, cursor, fonts, application style, and window decoration.
- Text, JSON, and redacted debug output.
- A read-only Qt capability view.
- Unit tests that run without KDE or Qt.

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
```

Run the test suite with:

```bash
pytest
```

The repository does not yet provide a distro package or portable release. See [PACKAGING.md](PACKAGING.md) for the current status.

## Safety boundary

Phase 0 contains no setting writers and always reports Apply as disabled. External commands are reviewed, read-only commands invoked as argument vectors without a shell. Debug output is generated locally and redacted before display; Alchemy does not upload it.

The transaction and rollback behavior described in the project direction is not implemented yet. Current limitations and tested targets are recorded in [COMPATIBILITY.md](COMPATIBILITY.md).

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
