# Rice format

The `.rice` v2 format is planned for Phase 4 and is not accepted or applied by the current build.

The format will be canonical UTF-8 JSON in a single document. It will describe desired state, compatibility, component settings, dependencies, immutable sources, licenses, and gallery metadata. It will not be a ZIP archive and may not contain scripts, commands, QML, binaries, fonts, images, symlinks, package hooks, secrets, or arbitrary paths to copy.

External assets and executable KDE components will be references handled by the dependency layer, not payloads embedded in the rice.

A normative JSON Schema, canonical serialization algorithm, hashing rules, hostile-input limits, and base/override merge behavior will be added with the implementation. No example in this document should be treated as a stable schema before that phase lands.
