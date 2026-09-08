# Security

Alchemy modifies desktop configuration, so a setting writer is security-sensitive code.

## Current state

The Phase 5 build permits a reviewed set of core Plasma mutations and semantic panel layouts when conservative capability checks pass. It acquires the shared lock before observing mutable state, snapshots the affected user file, persists the journal state before mutation, applies through a setting-specific KDE interface, verifies the observed state, and rolls back on failure. Rice import, resolution, and creator capture remain non-applying operations.

KConfig values reject control characters and enumerated values are allowlisted where upstream defines a closed set. Commands use argument vectors without a shell. Wallpaper paths must resolve to local regular files; wallpaper apply refuses layouts whose per-desktop state cannot be exactly reconstructed by the official KDE utility.

Panel JSON has strict fields, size/count bounds, identifier validation, and no command or widget-configuration field. Generated scripts embed only canonical JSON data. All requested and generated widgets are checked against Plasma's installed widget types before apply and again inside the apply script. Third-party plasmoids are treated as executable external dependencies and are never embedded or silently replaced.

Captured widget configuration can contain private local values. Transaction journals and snapshot artifacts use owner-only permissions on POSIX systems, and CLI plan, apply, revert, and recovery output excludes captured configuration and raw before/after values.

Rice v2 input is capped before parsing and then checked for duplicate keys, excessive nesting and collections, oversized strings and numbers, unsupported fields, non-HTTPS references, and invalid hashes. Canonical import verifies SHA-256 before storing bytes in an owner-only local directory. Hash-named cache entries are compared before reuse, and export refuses to overwrite an existing file.

Sparse overrides are separate from creator manifests and are bound to the base ID, version, and canonical hash. They can modify only component state, and the complete resolved document is revalidated. Import, export, inspection, and resolution never invoke a setting driver or install a dependency.

Creator capture accepts settings only from exact reviewed KConfig source mappings. Unknown observations are omitted. Panel capture consumes the public semantic view, which contains plugin identifiers but not widget configuration. Ambiguous multi-screen intent, custom panel lengths that cannot be represented exactly, and non-KDE widget provenance block panel export until the creator excludes or replaces that component.

Every generated manifest is structurally validated and scanned before publication. The scanner blocks local and home paths, local usernames and hostnames, email addresses, token-shaped values, OAuth/client-secret fields, private-key markers, recent-file/history fields, and known Wi-Fi names. Findings identify only a category and JSON path; unsafe values and the unsafe manifest are not printed. This is defense in depth, so creators must still review the draft.

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
