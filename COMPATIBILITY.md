# Compatibility

## Target policy

- KDE Plasma 6 only.
- Minimum v1 target: Plasma 6.6.
- Primary development target: Plasma 6.7 on Wayland.
- Plasma 6.8 Wayland compatibility is required before a v1 release.
- X11 is a legacy path for Plasma versions that still provide it.

Target distro testing includes Arch-family systems, Fedora KDE, KDE neon, and Kubuntu. openSUSE, immutable KDE variants, SteamOS Desktop Mode, and NixOS require capability-specific handling.

## Current evidence

Phase 0 through Phase 2 unit tests run on Windows without KDE. No real Plasma integration result has been recorded in this repository yet. The inspector is designed to report unavailable or unknown capabilities rather than claim support without evidence.

The color-scheme and Phase 2 core drivers are implemented for eligible Plasma 6.6-6.8 sessions. Their plan/apply/verify/rollback behavior is verified against fake KDE, DBus, and Plasma-shell boundaries; real KDE verification is still required. Drivers require `kreadconfig6` and `kwriteconfig6`, with official `plasma-apply-*` utilities required where used.

Wallpaper apply currently supports only local files and a uniform `org.kde.image` state across all desktops. A layout with different images, plugins, or supported fill modes per desktop is refused because KDE's command-line wallpaper utility would flatten that layout and could not restore it exactly. Font and cursor KConfig notifications are implemented, but XWayland propagation still needs real-session verification.

When adding an integration result, record the distro, exact Plasma version, session type, test date, and whether the behavior was documented or observed.
