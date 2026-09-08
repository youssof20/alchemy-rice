# Security

Alchemy modifies desktop configuration, so a setting writer is security-sensitive code.

## Current state

The Phase 1 build permits one color-scheme mutation when conservative capability checks pass. It snapshots the affected user file, persists the journal state before mutation, serializes mutations through a shared lock, applies through a reviewed KDE utility, verifies the observed state, and rolls back on failure. Other components remain read-only.

## Invariants

- A `.rice` is data, not an installer.
- Alchemy will never execute code contained in a rice manifest.
- External executable components are separate dependencies with explicit provenance and approval.
- Existing supported state must be captured before mutation.
- Only reviewed drivers may write configuration.
- Unknown dotfiles and widget configuration are not copied by default.
- Privileged operations remain separate from user-configuration transactions.
- A failed configuration transaction does not blindly uninstall packages.
- Remote artifacts must be pinned and hash-verified before trusted apply.

Third-party Plasma widgets, KWin effects, Global Themes, and login themes can contain executable code. Alchemy will not describe them as inert or safe merely because they affect appearance.

## Reporting a vulnerability

Do not include credentials, private configuration, or identifying debug data in a public issue. Until a private reporting channel is published, open a minimal public issue asking the maintainer for a private contact method. Include only the affected version and a non-sensitive summary.

No response-time guarantee has been established for this pre-alpha project.
