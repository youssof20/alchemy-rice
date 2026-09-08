# Creator capture workflow

Phase 5 can turn the current supported Plasma appearance state into a reviewable rice v2 draft. Capture is read-only and local. It does not apply settings, install packages, contact a repository, take screenshots, or upload output.

## Prepare source metadata

Copy `examples/capture-metadata.json` and replace every example value. The metadata declares the public rice identity, Semantic Version, author, HTTPS repository, release, and exact lowercase Git commit. It is not inferred from local Git state because source identity must be deliberate and immutable.

## Review a draft

Run:

```bash
alchemy capture-draft my-capture-metadata.json
```

The JSON result contains:

- `manifest`: the candidate rice, present only when the privacy scan passes;
- `included_components` and `excluded_components`;
- non-blocking limitations and blocking review findings;
- sanitizer categories and JSON paths without matched values;
- a Markdown summary suitable as a starting point for a README or Reddit post.

Capture uses exact visual-source mappings. It never copies a configuration file wholesale. Current wallpaper state is omitted because rice v2 requires an intentional HTTPS asset, SHA-256, and license. Effects and application-specific state are not yet in the reviewed capture allowlist.

Panel capture uses only public semantic inspection. Widget configuration is excluded. Built-in KDE widget identifiers are preserved. A non-KDE widget requires explicit dependency source and license metadata, while non-primary screen assignments and custom lengths need deliberate portable intent. These cases block panel export instead of guessing.

Use a repeatable exclusion after review:

```bash
alchemy capture-draft my-capture-metadata.json --exclude panels --exclude apps
```

An exclusion is an explicit creator choice. It does not delete or alter the current desktop.

## Export

Once `export_ready` is true, run the same selection through canonical export:

```bash
alchemy capture-export my-capture-metadata.json my-rice.rice --exclude panels
```

Export reruns inspection, validation, and sanitization. It writes canonical rice bytes to a new `.rice` path and refuses to overwrite an existing file. Review the returned hash and human-readable summary before publishing either artifact.

## Privacy checks

The publication scanner blocks home and absolute paths, local usernames, local hostnames, email addresses, credential-shaped values, OAuth/client-secret fields, SSH/private-key markers, recent-file/history keys, and known Wi-Fi names supplied by an embedding caller. Unsafe drafts do not print the candidate manifest or summary.

Sanitization is defense in depth. A creator remains responsible for reviewing names, URLs, licenses, compatibility claims, dependencies, screenshots, and all public text before release.
