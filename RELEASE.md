# Release evidence and gates

Alchemy is not beta-ready. `v0.1.0a1` is an explicitly experimental prerelease for maintainer-led
testing, not evidence that a distro install has succeeded. No real Plasma apply/revert recording or
external beta report is currently claimed.

The versioned evidence document at `release/evidence-v1.json` is the single release ledger. Check it
without changing the system:

```bash
alchemy release-check release/evidence-v1.json
alchemy release-check release/evidence-v1.json --require beta
alchemy release-check release/evidence-v1.json --require launch
```

The first command reports every missing gate and exits successfully when the document is valid. The
`--require` forms also fail until the requested gate passes, making them suitable for a release
review or CI job. Evidence URLs must be public HTTPS links. Do not put names, email addresses, local
paths, raw logs containing identity, or credentials in the ledger.

## Beta gate

A public beta may begin only after all of these are recorded against one exact public commit:

- Arch and Debian packages each build, install, run `alchemy --help` and `alchemy app-list`, and
  uninstall cleanly on their target distro;
- Arch Plasma 6.7 Wayland and at least one non-Arch KDE baseline pass;
- every destructive recovery scenario in the evidence matrix passes;
- all required public documentation and package paths are present.

A `passed` or `failed` status requires a public evidence URL. `pending` is the only status allowed
without one. A failed result remains visible and blocks the gate until a later public report records
the fixed run.

## VM and destructive matrix

The fixed VM identifiers cover Arch, current Fedora KDE, KDE neon during the Plasma Login Manager
transition, Kubuntu, Plasma 6.8 Wayland, physical mixed-scale multi-monitor hardware, and
NixOS/plasma-manager ownership. Record the exact Plasma version observed; do not infer one from the
distro name.

Each VM report should include package installation, read-only inspection, representative plan and
apply operations, verification, revert, restart recovery, capture/export, and app-adapter behavior.
The destructive list separately requires process interruption, forced verification failure,
unwritable snapshots, dependency drift, incomplete-journal recovery, malformed and hash-mismatched
rice files, symlink refusal, and repository secret fixtures.

## Launch gate

The launch gate includes every beta requirement and additionally requires:

- every VM or hardware matrix entry passed;
- at least five public external beta reports across multiple distros and at least two Plasma point
  releases;
- a passed import/apply report for one pinned community-style rice without executing repository
  code;
- a real 20–40 second Plasma 6.7 Wayland recording that visibly demonstrates apply, verification,
  and revert with multiple applications on screen.

The recording entry includes its SHA-256 and must mark `generated_visuals` false. A mockup,
generated render, edited claim without the actual transaction, or Alchemy-only window does not
satisfy the gate. The repository deliberately contains no launch-post automation: publication is a
manual maintainer decision after `launch_ready` is true and the evidence has been reviewed.

## Recording procedure

Use a disposable but real Plasma 6.7 Wayland test account with no private notifications or files.
Show the starting desktop, the exact plan, apply, successful verification, changed real
applications, revert, and the restored desktop. Keep the original recording, calculate its hash
with `sha256sum`, upload it to the matching public release, then record that immutable release URL
and hash. Review every frame for personal data before publication.

## Updating evidence

Copy the pending ledger forward for a release candidate, change `release` and `source_commit`, and
replace pending records only with results from that exact commit. Keep issue reports and CI logs
public and durable. The schema and runtime validator reject missing matrix identifiers, duplicates,
insecure URLs, unknown fields, oversized input, and incomplete non-pending records.
