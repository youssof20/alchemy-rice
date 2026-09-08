# Alchemy

Alchemy is a completely free, GPL-licensed KDE Plasma 6 ricing workbench under active development. The current Phase 10 development build targets Plasma 6.6 through 6.8, previews and transactionally applies reviewed appearance, panel, and application settings, and restores targeted snapshots when verification fails. A `.rice` is declarative configuration: Alchemy does not execute scripts or binaries from it.

Source, wheel, Arch VCS, and Debian-family build paths are documented in [PACKAGING.md](PACKAGING.md). No package or beta has been published, no real Plasma integration recording exists yet, and the evidence gate in [RELEASE.md](RELEASE.md) intentionally blocks beta and launch claims until the required multi-distro results are public.

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
- Creator capture from an exact visual-setting allowlist; arbitrary dotfiles, app state, and widget configuration are never included.
- Reviewable capture drafts with component exclusions, portable panel conversion, and unresolved-component findings.
- Blocking publication scans for local paths, usernames, hostnames, email addresses, credential patterns, private-key markers, history keys, and known Wi-Fi names.
- Canonical capture export plus a human-readable component, compatibility, dependency, and limitation summary.
- Tier A/B/C dependency classification with exact source, package, version, privilege, and command review data.
- Read-only dependency checks and provider-specific plans for pacman, AUR helpers, dnf, apt, and zypper.
- Separate, token-bound installation of reviewed official packages with post-install verification and local receipts.
- Versioned compatibility data that distinguishes confirmed, broken, unknown, unsupported, and user-report evidence.
- Strict gallery entry and static snapshot schemas with bounded hostile-input parsing.
- Creator-owned GitHub and Codeberg release validation using pinned commits and SHA-256 values.
- Remote CI verification of ownership challenges, canonical rice projections, screenshot hashes, and bounded image headers without executing contributor code.
- Deterministic static snapshot generation with maintainer-owned metrics and derived objective badges.
- An ETag-aware local gallery cache, offline search, five explainable sorts, and a cached Qt browser.
- Local compatibility report previews that generate a prefilled GitHub URL without opening it or uploading data.
- HTTPS-only, commit-pinned repository import into an isolated bounded bare-Git cache with no checkout, hooks, submodules, or contributor-code execution.
- Static recognizers for reviewed KDE settings, color schemes, app-config references, wallpaper references, package lists, and script filenames.
- Sanitized rice draft conversion with conflict omission, unresolved-provenance findings, and a separate unsupported-content report.
- Versioned, transactional visual adapters for Konsole, Kitty, Starship, and fastfetch with complete-file ownership and mixed-config refusal.
- Static conversion of the same reviewed application subsets during repository import.
- PEP 639 Python distribution metadata, desktop integration assets, and checked Arch VCS and Debian-family development packaging paths.
- A strict release-evidence ledger with separate beta and launch gates for native packages, the VM and destructive matrix, external reports, a community rice, and a real recording.
- Read-only `release-check` reporting and CI quality/distribution checks that do not publish a release.
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
alchemy capture-draft examples/capture-metadata.json
alchemy capture-draft examples/capture-metadata.json --exclude panels
alchemy capture-export examples/capture-metadata.json captured-workbench.rice
alchemy rice-export examples/rice-v2-dependencies.json kvantum-workbench.rice
alchemy dependency-resolve kvantum-workbench.rice
alchemy dependency-install kvantum-workbench.rice kvantum-style-engine --plan-token TOKEN --yes
alchemy gallery-validate gallery/entries
alchemy gallery-build gallery/entries gallery.json --metrics gallery/metrics.json --check
alchemy gallery-cache gallery.json
alchemy gallery-list --sort compatible
alchemy gallery
alchemy gallery-report ENTRY_ID --result success
alchemy repo-import https://github.com/example/dotfiles.git COMMIT examples/repository-import-metadata.json
alchemy repo-import https://github.com/example/dotfiles.git COMMIT examples/repository-import-metadata.json --draft imported.rice
alchemy app-list
alchemy app-inspect kitty
alchemy plan-app kitty examples/apps/kitty.json
alchemy apply-app kitty examples/apps/kitty.json --plan-token TOKEN_FROM_PLAN --yes
alchemy release-check release/evidence-v1.json
alchemy release-check release/evidence-v1.json --require beta
alchemy revert --last
alchemy recovery --list
```

Run the test suite with:

```bash
pytest
```

The repository provides development package definitions but no published distro package or portable release. See [PACKAGING.md](PACKAGING.md) and [RELEASE.md](RELEASE.md) for the current blockers.

## Safety boundary

Writers are unavailable unless the host is Linux, an active KDE session reports a version in the current 6.6-6.8 target window, plasma-manager is not detected as the state owner, and each driver's required KDE tools exist. External commands are invoked as argument vectors without a shell. Debug output is generated locally and redacted before display; Alchemy does not upload it.

The transaction, driver, capture, package-provider, gallery-network, repository-import, and application-adapter behavior has fake-boundary unit coverage but has not yet been validated in a real Plasma VM. Current limitations and test evidence are recorded in [COMPATIBILITY.md](COMPATIBILITY.md). Setting names and accepted values are documented in [SETTING_REFERENCE.md](SETTING_REFERENCE.md); panel layout fields are documented in [PANEL_LAYOUT.md](PANEL_LAYOUT.md), creator review in [CAPTURE_WORKFLOW.md](CAPTURE_WORKFLOW.md), dependency trust and installation in [DEPENDENCY_RESOLUTION.md](DEPENDENCY_RESOLUTION.md), gallery submission and caching in [GALLERY.md](GALLERY.md), the dotfile bridge in [REPOSITORY_IMPORT.md](REPOSITORY_IMPORT.md), and app file ownership in [APP_ADAPTERS.md](APP_ADAPTERS.md).

## Project documents

- [ARCHITECTURE.md](ARCHITECTURE.md)
- [SECURITY.md](SECURITY.md)
- [PRIVACY.md](PRIVACY.md)
- [CONTRIBUTING.md](CONTRIBUTING.md)
- [RICE_FORMAT.md](RICE_FORMAT.md)
- [SETTING_REFERENCE.md](SETTING_REFERENCE.md)
- [PANEL_LAYOUT.md](PANEL_LAYOUT.md)
- [CAPTURE_WORKFLOW.md](CAPTURE_WORKFLOW.md)
- [DEPENDENCY_RESOLUTION.md](DEPENDENCY_RESOLUTION.md)
- [GALLERY.md](GALLERY.md)
- [REPOSITORY_IMPORT.md](REPOSITORY_IMPORT.md)
- [APP_ADAPTERS.md](APP_ADAPTERS.md)
- [RELEASE.md](RELEASE.md)
- [COMPATIBILITY.md](COMPATIBILITY.md)
- [PACKAGING.md](PACKAGING.md)
- [CHANGELOG.md](CHANGELOG.md)

No real apply/revert recording exists yet. A real Plasma recording will replace this note after the implemented drivers pass KDE integration testing.
