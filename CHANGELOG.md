# Changelog

All notable project changes will be recorded here. The project has not made a public release.

## Unreleased

## 0.1.0a2 - 2026-09-09

- Published the first test-only Python wheel and source archive.
- Reworked the README around exact distro prerequisites, a short install path, a safe first
  transaction, supported Plasma versions, and clearly separated feature and limitation lists.
- Kept strict type checking compatible with the mypy 1.x range used by clean Linux builds.

## 0.1.0a1 - 2026-09-09

- Tagged for an initial release attempt, but CI stopped before artifacts were published.

### Phase 10 — packaging and evidence-gated beta preparation

- Added PEP 639 metadata, explicit license inclusion, project URLs, desktop entry, AppStream
  metadata, scalable icon, and complete source-distribution inputs.
- Added an Arch `alchemy-rice-git` PKGBUILD using the system PEP 517 build and installer tools.
- Added Debian-family debhelper/pybuild packaging and a command-line autopkgtest.
- Added a strict release-evidence v1 schema, bounded runtime parser, fixed VM and destructive-test
  matrices, and independently derived beta and launch readiness.
- Added release gates for native package smoke tests, public evidence URLs, multi-distro and
  multi-Plasma external reports, a pinned community rice, and a real hashed apply/revert recording.
- Added read-only release-check CLI output plus a failing `--require beta|launch` mode for release
  review and CI.
- Added a pinned, read-only GitHub quality workflow that lints, type-checks, tests, builds wheel and
  source distributions, checks metadata, and records hashes without publishing artifacts.
- Documented that every real-system, package, beta, recording, and launch gate remains pending.

### Phase 9 — application adapters

- Added versioned visual schemas and strict parsers for Konsole, Kitty, Starship, and fastfetch.
- Added complete-file ownership with symlink refusal, mixed-config refusal, atomic writes, semantic
  verification, exact snapshots, durable journals, recovery, and rollback.
- Added token-bound app inspection, planning, apply, and revert CLI workflows without starting or
  reloading applications.
- Restricted Kitty includes, Starship command-capable modules, fastfetch identity fields and object
  modules, path-based logos, and every non-visual or behavioral field.
- Added static repository conversion for the same reviewed subsets with ignored-field reporting and
  conflict omission.
- Added app examples, format and safety documentation, and fake-boundary coverage for round trips,
  stale plans, new-file rollback, mixed configs, and missing executables.

### Phase 8 — dotfile repository import

- Added HTTPS-only import of full pinned commits from public GitHub and Codeberg repositories.
- Added a bounded bare-Git cache with isolated configuration, disabled hooks and non-HTTPS
  transports, shallow blob-filtered fetches, and no working-tree checkout.
- Added static recognizers for reviewed KDE KConfig fields and KDE color-scheme names.
- Added deferred recognition for Kvantum, Konsole, Kitty, Alacritty, Ghostty, Starship, and
  fastfetch configuration without copying or applying it; Phase 9 later promotes the reviewed
  Konsole, Kitty, Starship, and fastfetch subsets.
- Added wallpaper references, package-list candidates, script filename reporting, symlink and
  submodule refusal, and a separate unsupported-content inventory.
- Added publication scanning, sensitive-file omission, personal-path redaction, conflict omission,
  provenance and license findings, and validated no-overwrite rice draft output.
- Added CLI documentation, example metadata, and tests for input boundaries, mapping, reporting,
  selective reads, command construction, and non-applying behavior.

### Phase 7 — community gallery

- Added strict gallery entry and static snapshot schemas with duplicate-key and hostile-input limits.
- Added GitHub and Codeberg source ownership proofs derived from a full pinned commit.
- Added safe remote verification of canonical rice projections, release hashes, screenshot hashes,
  supported image headers, compatibility declarations, and license metadata.
- Added a pull-request workflow that runs trusted base-revision validation while treating the
  contributor checkout only as data.
- Added deterministic snapshot generation with a source digest, maintainer-owned metrics, and
  explainable derived badges.
- Added explicit ETag-aware snapshot refresh, integrity-checked local cache import, offline search,
  detail views, and five documented sorts without per-card API calls.
- Added a cached Qt gallery browser and local compatibility report previews that generate a
  prefilled GitHub form URL without opening it or uploading data.
- Added fake-boundary tests for remote tampering, ownership, cache reuse, offline behavior,
  deterministic output, reports, and hostile metadata.

### Phase 6 — dependency resolver

- Added explicit Tier A distribution, Tier B community, and Tier C manual trust classifications and user-facing labels.
- Added strict, versioned Plasma, component, and distro-package compatibility databases with dated evidence states.
- Added provider adapters and exact command planning for pacman, paru/yay, dnf, apt, and zypper.
- Added read-only installed-package inspection and declared-version checks.
- Added immutable/Nix host refusal, missing-provider results, manual-source handling, and explicit known-incompatibility overrides.
- Added review tokens bound to the rice hash, environment, compatibility result, package candidate, and command.
- Added a separate confirmed Tier A install command using `pkexec`, followed by provider verification and an owner-only local receipt.
- Kept Tier B/AUR operations visible but manual and prohibited package auto-uninstall during rice rollback.
- Added fake-boundary coverage for trust classification, provider plans, stale-token refusal, immutable hosts, manual sources, known breakage, verified installation, and receipts.

### Phase 5 — creator capture and sanitizer

- Expanded read-only inspection to all 18 reviewed KConfig settings backed by existing core drivers.
- Added exact source-to-rice visual allowlists and conservative value conversion.
- Added portable panel capture from public semantic state without widget configuration values.
- Added explicit blocking findings for ambiguous screen intent, unavailable custom lengths, and unresolved non-KDE widget provenance.
- Added recursive publication scanning for local paths, identities, emails, credential patterns, private keys, history fields, and known Wi-Fi names without echoing matches.
- Added review and export CLI workflows with repeatable component exclusions.
- Added canonical, no-overwrite capture export and a Markdown component/dependency summary.
- Added fake-boundary coverage for safe capture, unsupported settings, panel conversion, environment gating, canonical export, and secret redaction.

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
