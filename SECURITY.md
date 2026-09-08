# Security

Alchemy modifies desktop configuration, so a setting writer is security-sensitive code.

## Current state

The Phase 9 build permits a reviewed set of core Plasma mutations, semantic panel layouts, and narrowly owned application visual files when conservative capability checks pass. It acquires the shared lock before observing mutable state, snapshots the affected user file, persists the journal state before mutation, applies through a setting-specific interface, verifies the observed state, and rolls back on failure. Rice import, creator capture, gallery browsing, and repository import remain non-applying operations. Dependency installation is a separate explicit operation.

KConfig values reject control characters and enumerated values are allowlisted where upstream defines a closed set. Commands use argument vectors without a shell. Wallpaper paths must resolve to local regular files; wallpaper apply refuses layouts whose per-desktop state cannot be exactly reconstructed by the official KDE utility.

Application adapters write only one exact path under the user's XDG configuration or data root.
They refuse symlinked paths, unknown existing keys, include directives, command-capable Starship
modules, path-based fastfetch logos, identity-revealing fastfetch modules, and behavioral terminal
configuration. An app is never started or reloaded by Alchemy. The application executable must
already be present, and dependencies remain a separate reviewed workflow.

Panel JSON has strict fields, size/count bounds, identifier validation, and no command or widget-configuration field. Generated scripts embed only canonical JSON data. All requested and generated widgets are checked against Plasma's installed widget types before apply and again inside the apply script. Third-party plasmoids are treated as executable external dependencies and are never embedded or silently replaced.

Captured widget configuration can contain private local values. Transaction journals and snapshot artifacts use owner-only permissions on POSIX systems, and CLI plan, apply, revert, and recovery output excludes captured configuration and raw before/after values.

Rice v2 input is capped before parsing and then checked for duplicate keys, excessive nesting and collections, oversized strings and numbers, unsupported fields, non-HTTPS references, and invalid hashes. Canonical import verifies SHA-256 before storing bytes in an owner-only local directory. Hash-named cache entries are compared before reuse, and export refuses to overwrite an existing file.

Sparse overrides are separate from creator manifests and are bound to the base ID, version, and canonical hash. They can modify only component state, and the complete resolved document is revalidated. Import, export, inspection, and resolution never invoke a setting driver or install a dependency.

Creator capture accepts settings only from exact reviewed KConfig source mappings. Unknown observations are omitted. Panel capture consumes the public semantic view, which contains plugin identifiers but not widget configuration. Ambiguous multi-screen intent, custom panel lengths that cannot be represented exactly, and non-KDE widget provenance block panel export until the creator excludes or replaces that component.

Every generated manifest is structurally validated and scanned before publication. The scanner blocks local and home paths, local usernames and hostnames, email addresses, token-shaped values, OAuth/client-secret fields, private-key markers, recent-file/history fields, and known Wi-Fi names. Findings identify only a category and JSON path; unsafe values and the unsafe manifest are not printed. This is defense in depth, so creators must still review the draft.

Dependency trust comes from reviewed compatibility data, not from a rice's claim. Official distro mappings are Tier A. AUR, community repositories, KDE Store packages, and GitHub releases are never labeled official. Manual sources and mappings without reviewed evidence cannot produce an automatic plan. Immutable and Nix-managed hosts refuse host package mutation.

Install commands are fixed argument vectors, never manifest-provided strings and never shell commands. Privileged Tier A plans use `pkexec` explicitly and explain why privilege is required. The user must provide both `--yes` and a token from the reviewed plan. The service acquires the shared mutation lock, resolves again, rejects any token drift, invokes one provider, and verifies the installed package before recording a receipt. Command output is not echoed in errors. Tier B and Tier C sources remain manual in this phase.

Package installation is intentionally outside the configuration transaction. A rice revert never blindly uninstalls a package because it may predate Alchemy or be shared by other applications. Receipts record what Alchemy installed so a future guided cleanup can make an informed, separate decision.

Gallery entry and snapshot inputs have byte, tree, collection, string, identifier, date, and URL
limits. Gallery v1 permits only source-owned GitHub or Codeberg release assets and commit-pinned raw
screenshots. Remote validation fetches a derived ownership challenge, a canonical rice, and bounded
PNG/JPEG/WebP bytes; it compares hashes and rice projections without running repository content.

Pull-request validation executes the validator from the trusted base revision. The contributor
checkout is neither installed nor imported, credentials are not persisted, and the job has a
read-only token. Snapshot replacement occurs only after full validation. Redirect destinations are
restricted to the expected forge or its release-asset hosts, and an unexpected hash blocks reuse.

Repository import accepts only a plain public GitHub or Codeberg HTTPS URL and a full lowercase
commit SHA. It creates a bare cache from an empty template and does not create a checkout. Git's
global and system configuration are disabled, hooks point to the null device, non-HTTPS transports
are denied, TLS verification is required, and redirects are limited to the initial request. Fetches
are shallow, tag-free, submodule-free, blob-filtered, time-bounded, output-bounded, and monitored
against a cache-size cap.

Tree entries are parsed before content access. Symlinks and submodules are never followed;
executables are never read or run; sensitive filenames are not read; and unsupported or binary
files are not copied. Only size-bounded static text candidates are read by object ID, with a second
cap on total analyzed bytes. Recognizers accept exact visual keys rather than arbitrary KConfig.
Scripts are reported by filename only. Credential-shaped content is quarantined, personal paths are
redacted from reports, conflicting settings are omitted, and the generated draft is validated and
sanitized again. A repository import never invokes a build system, package manager, setting driver,
or shell.

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

Release evidence is untrusted bounded JSON and is validated without fetching its URLs. A recorded
URL is provenance for human review, not proof by itself. Release tooling is read-only: it cannot
publish a package, upload a recording, create a release, or post launch material. Package and launch
decisions remain explicit maintainer actions after the referenced evidence is reviewed.

## Reporting a vulnerability

Do not include credentials, private configuration, or identifying debug data in a public issue. Until a private reporting channel is published, open a minimal public issue asking the maintainer for a private contact method. Include only the affected version and a non-sensitive summary.

No response-time guarantee has been established for this pre-alpha project.
