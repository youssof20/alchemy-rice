# Compatibility

## Target policy

- KDE Plasma 6 only.
- Minimum v1 target: Plasma 6.6.
- Primary development target: Plasma 6.7 on Wayland.
- Plasma 6.8 Wayland compatibility is required before a v1 release.
- X11 is a legacy path for Plasma versions that still provide it.

Target distro testing includes Arch-family systems, Fedora KDE, KDE neon, and Kubuntu. openSUSE, immutable KDE variants, SteamOS Desktop Mode, and NixOS require capability-specific handling.

## Current evidence

Phase 0 and Phase 1 unit tests run on Windows without KDE. No real Plasma integration result has been recorded in this repository yet. The inspector is designed to report unavailable or unknown capabilities rather than claim support without evidence.

The color-scheme driver is implemented for eligible Plasma 6.6-6.8 environments with `kreadconfig6` and `plasma-apply-colorscheme`. Its transaction behavior is verified against a fake KDE boundary; real KDE verification is still required. All other drivers are read-only.

When adding an integration result, record the distro, exact Plasma version, session type, test date, and whether the behavior was documented or observed.
