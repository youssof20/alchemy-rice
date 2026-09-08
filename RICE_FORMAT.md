# Rice format v2

A `.rice` is a single canonical UTF-8 JSON document containing declarative configuration and external resource references. It is not an archive, installer, repository, or executable package.

The normative schemas are [rice-v2.schema.json](schemas/rice-v2.schema.json) and [rice-override-v1.schema.json](schemas/rice-override-v1.schema.json). Alchemy also applies semantic checks that JSON Schema cannot express cleanly, including satisfiable Plasma version ranges, unique panel IDs, custom panel-length rules, dependency identity uniqueness, mutually exclusive effect lists, and base-hash binding for overrides.

Phase 4 validates, inspects, resolves, exports, and locally imports these documents. It does not apply a complete rice. Component planning, dependency resolution, and combined transactional apply are later phases.

## Root document

Every root field is required. Unknown fields are rejected.

| Field | Meaning |
| --- | --- |
| `$schema` | Exact v2 schema URI. |
| `schema_version` | Integer `2`. |
| `id` | Stable creator-controlled rice identifier. |
| `name` | Human-readable name. |
| `version` | Semantic Version 2.0 value. |
| `author` | Author name and optional HTTPS URL. |
| `source` | HTTPS repository, release name, and full lowercase Git commit. |
| `compatibility` | Plasma range, allowed sessions, optional distros, and tested environments. |
| `components` | Supported declarative visual component values. |
| `dependencies` | External config, asset, or executable component references. |
| `licenses` | SPDX identifiers, covered component IDs, and source URLs. |
| `gallery` | Hashed screenshot references plus optional Reddit and tip URLs. |

See [rice-v2-draft.json](examples/rice-v2-draft.json) for a readable source document. Export converts it to canonical `.rice` bytes:

```bash
alchemy rice-export examples/rice-v2-draft.json night-workbench.rice
```

## Components

The initial v2 implementation recognizes only these keys:

- `colors`
- `fonts`
- `icons`
- `cursor`
- `plasma_theme`
- `application_style`
- `window_decoration`
- `kwin`
- `panels`
- `effects`
- `wallpaper`
- `apps`

Each component is strict. Unknown component keys or settings are rejected rather than retained as opaque state. `apps` must currently be empty because no reviewed application adapter exists yet.

Panel declarations reuse the semantic Phase 3 model described in [PANEL_LAYOUT.md](PANEL_LAYOUT.md). The component contains `{"panels": [...]}` without the standalone panel file's `format_version` field.

Wallpaper and gallery images are HTTPS references with lowercase SHA-256 values; media bytes are never embedded. Third-party widgets, effects, style engines, and other executable components are dependency references only. Dependencies contain identities and source metadata, never installation commands or package hooks.

## Canonical JSON and hashes

Canonical serialization is deterministic:

1. Input is decoded as UTF-8 without a byte-order mark.
2. Duplicate object keys and non-finite numbers are rejected.
3. Object keys are sorted by Unicode code-point order.
4. Array order is preserved.
5. Strings use JSON escaping only where required and otherwise remain UTF-8.
6. Numbers use base-10 notation without an exponent, insignificant trailing zeroes, or negative zero.
7. No insignificant whitespace or trailing newline is emitted.

The rice SHA-256 is calculated over those exact canonical bytes. Import requires the source `.rice` file itself to be canonical, so its file hash and canonical hash are identical. Pretty or unordered JSON must first pass through `rice-export`.

Documents are capped at 1 MiB, 10,000 JSON nodes, 32 nesting levels, 2,048 entries per array, 256 keys per object, and 4,096 characters per general string. Smaller field-specific limits also apply. Canonical numbers are limited to 100 significant digits and decimal exponents between -308 and 308.

## Overrides

User customization is stored separately from its base rice. An override contains:

```json
{
  "override_version": 1,
  "base": {
    "id": "github:example/alchemy-rice:night-workbench",
    "version": "1.0.0",
    "sha256": "b545f8af557dd716403e8f39135295c41d4646b31e42f4898dd0c2202e41a532"
  },
  "components": {
    "cursor": {"size": 48}
  }
}
```

The base ID, version, and SHA-256 must all match before resolution. Overrides can change only `components`; they cannot rewrite creator identity, source, compatibility claims, dependencies, licenses, or gallery metadata. Object fields merge recursively, arrays and scalar values replace their base value, and `null` removes a field. The final result must still pass the complete rice validator.

`rice-resolve` reports the computed components plus JSON-pointer provenance for base and override leaves. The resolved hash identifies the local computed view; it is not the creator's published rice hash.

## Compatibility evaluation

Plasma ranges use comma-separated clauses such as `>=6.6,<6.9`. Supported operators are `>=`, `>`, `<=`, `<`, and `==`; impossible ranges are rejected.

The local evaluator reports `compatible`, `compatible_with_warnings`, `incompatible`, or `unknown`. It checks Linux/KDE, detected Plasma and the current engine's 6.6-6.8 window, Wayland/X11 declarations, optional distro restrictions, plasma-manager ownership, Union requirements, mixed-scale panel review, mutable source release names, and unresolved dependencies. Missing evidence remains `unknown` rather than being guessed.

Compatibility declarations and `tested` entries are author claims, not proof that a rice works on every matching system.

## Commands

```bash
alchemy rice-inspect FILE.rice --sha256 EXPECTED_HASH
alchemy rice-export SOURCE.json NEW_FILE.rice
alchemy rice-resolve BASE.rice OVERRIDE.json
alchemy rice-import FILE.rice --sha256 EXPECTED_HASH --override OVERRIDE.json
```

Import stores verified canonical bytes under their SHA-256 in the local Alchemy data directory and reports `"applied": false`. Existing hash-named cache entries are read back and compared before reuse. Export never overwrites an existing destination.

## Forbidden content

A rice cannot contain scripts, commands, QML, binaries, fonts, image payloads, archives, symlinks, credentials, arbitrary local copy paths, package-manager hooks, or executable plugin definitions. URLs must use HTTPS without embedded credentials or fragments. External executable components remain visible dependencies for the separate trust and installation workflow.
