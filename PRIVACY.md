# Privacy

Alchemy does not include telemetry or an analytics SDK.

The Phase 0 inspector reads local environment facts and a reviewed set of KDE appearance settings. It does not upload them. `alchemy debug-info` produces a local preview and redacts the current username, home path, hostname, IP addresses, MAC addresses, and common token-shaped values before printing.

Imported rice manifests and optional overrides are stored locally by canonical SHA-256. Rice commands do not upload manifests, compatibility results, environment data, or overrides. URLs in a rice are validated as data but are not fetched during Phase 4 import or inspection.

Creator capture reads only the reviewed visual settings and the panel driver's public semantic result. It does not capture arbitrary dotfiles, recent files, application state, or widget configuration. Draft and export commands are local-only and do not take screenshots, query Wi-Fi networks, contact repositories, or upload output. If a caller explicitly supplies known Wi-Fi names to the sanitizer, matching strings are blocked.

Future network access will be tied to a visible user action such as fetching the gallery snapshot, importing a public repository, checking for a release when enabled, or downloading an approved dependency. Screenshots, rice exports, configuration, package lists, and failure reports will not be uploaded automatically.

Debug redaction and capture sanitization are safety aids, not guarantees. Review output before posting it publicly.
