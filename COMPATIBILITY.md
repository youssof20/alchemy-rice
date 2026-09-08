# Compatibility

## Target policy

- KDE Plasma 6 only.
- Minimum v1 target: Plasma 6.6.
- Primary development target: Plasma 6.7 on Wayland.
- Plasma 6.8 Wayland compatibility is required before a v1 release.
- X11 is a legacy path for Plasma versions that still provide it.

Target distro testing includes Arch-family systems, Fedora KDE, KDE neon, and Kubuntu. openSUSE, immutable KDE variants, SteamOS Desktop Mode, and NixOS require capability-specific handling.

## Current evidence

Phase 0 through Phase 4 unit tests run on Windows without KDE. No real Plasma integration result has been recorded in this repository yet. The inspector is designed to report unavailable or unknown capabilities rather than claim support without evidence.

The color-scheme and Phase 2 core drivers are implemented for eligible Plasma 6.6-6.8 sessions. Their plan/apply/verify/rollback behavior is verified against fake KDE, DBus, and Plasma-shell boundaries; real KDE verification is still required. Drivers require `kreadconfig6` and `kwriteconfig6`, with official `plasma-apply-*` utilities required where used.

Wallpaper apply currently supports only local files and a uniform `org.kde.image` state across all desktops. A layout with different images, plugins, or supported fill modes per desktop is refused because KDE's command-line wallpaper utility would flatten that layout and could not restore it exactly. Font and cursor KConfig notifications are implemented, but XWayland propagation still needs real-session verification.

Panel layout behavior is implemented against the Plasma 6.6-6.8 scripting properties and `dumpCurrentLayoutJS` interface. Fake-boundary coverage includes strict parsing, screen-role expansion, dimension clamping, widget dependency refusal, ordered apply, semantic verification, captured-configuration rollback, and transaction-level automatic restoration. Primary-screen index behavior, multi-monitor hotplug, third-party plasmoids, all visibility modes, and asynchronous panel-view settling still require real Wayland and X11 sessions. Panel apply therefore remains gated to the supported Plasma window and refuses a preview token after any observed state or mapping change.

Rice v2 parsing, canonicalization, hashing, overrides, local import/export, and compatibility rules are platform-independent and have Windows unit coverage. Compatibility results rely on detected local evidence and author declarations; they do not replace real-session testing. Dependency presence and package compatibility are intentionally reported as unresolved until the dependency layer is implemented. A complete rice cannot yet be planned or applied as one transaction.

When adding an integration result, record the distro, exact Plasma version, session type, test date, and whether the behavior was documented or observed.
