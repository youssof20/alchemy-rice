# Repository import

`alchemy repo-import` converts a small, reviewed subset of a public dotfile repository into a
local rice draft. It analyzes one full commit SHA and never applies the result.

```bash
alchemy repo-import \
  https://github.com/example/dotfiles.git \
  aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa \
  examples/repository-import-metadata.json \
  --draft imported.rice
```

The metadata file supplies the identity, author, compatibility claim, immutable source binding,
and license declarations required by rice v2. Its `source.repo` and `source.commit` values must
exactly match the command. Replace the illustrative values in the example before importing.

## What the importer recognizes

The current reviewed mappings cover these KDE files and fields:

- `kdeglobals`: color scheme, six font roles, icon theme, and application style;
- `kcminputrc`: cursor theme and size;
- `plasmarc`: Plasma theme;
- `kwinrc`: window decoration plus selected placement and maximized-border behavior;
- KDE `.colors` files: the declared scheme name.

Reviewed visual subsets from Konsole profiles, Kitty, Starship, and fastfetch are mapped into
`components.apps`. Behavioral and unsupported fields remain report findings. Kvantum, Konsole color
scheme assets, Alacritty, and Ghostty remain recognized references pending further adapters.
Wallpapers are references only until their immutable source, hash, and redistribution license are supplied. Plain `packages`, `packages.txt`,
`pkglist.txt`, and `dependencies.txt` files produce untrusted dependency candidates for later
review; they never produce installation commands.

Every unsupported file is listed with a reason. Conflicting supported settings are omitted rather
than resolved using repository path or traversal order. Findings explain unresolved component
provenance, license work, personal paths, credential-shaped text, unsupported settings, and
adapter gaps. A draft may be written only after the generated manifest itself passes publication
sanitization. Blocking review findings still make `export_ready` false.

## Repository boundary

Version 1 accepts plain HTTPS URLs for public GitHub and Codeberg repositories and requires a full
lowercase 40-character commit SHA. Git runs against an isolated bare cache:

- no working tree is created;
- global and system Git configuration is disabled;
- hooks use an empty path;
- only HTTPS transport is enabled;
- the fetch is shallow, tag-free, submodule-free, and blob-filtered;
- fetch time, command output, repository size, file count, per-file bytes, and analyzed text bytes
  are bounded.

Alchemy reads blobs by object ID after inspecting the pinned tree. It never runs hooks, installer
scripts, build systems, repository binaries, shell fragments, submodules, or symlink targets.
Executable files and scripts are named in the report without semantic safety claims. Sensitive
filenames are not read. Binary wallpapers are not decoded or copied. Unknown dotfiles are not
copied.

The importer is not a deployment front end for chezmoi, GNU Stow, yadm, Home Manager, or arbitrary
shell installers. It produces data for review; applying supported fields remains a separate
transactional workflow.
