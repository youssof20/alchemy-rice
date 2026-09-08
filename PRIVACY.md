# Privacy

Alchemy does not include telemetry or an analytics SDK.

The Phase 0 inspector reads local environment facts and a reviewed set of KDE appearance settings. It does not upload them. `alchemy debug-info` produces a local preview and redacts the current username, home path, hostname, IP addresses, MAC addresses, and common token-shaped values before printing.

Imported rice manifests and optional overrides are stored locally by canonical SHA-256. Rice commands do not upload manifests, compatibility results, environment data, or overrides. URLs in a rice are validated as data but are not fetched during Phase 4 import or inspection.

Creator capture reads only the reviewed visual settings and the panel driver's public semantic result. It does not capture arbitrary dotfiles, recent files, application state, or widget configuration. Draft and export commands are local-only and do not take screenshots, query Wi-Fi networks, contact repositories, or upload output. If a caller explicitly supplies known Wi-Fi names to the sanitizer, matching strings are blocked.

Application inspection reads only the exact owned Konsole, Kitty, Starship, or fastfetch file and
returns only its reviewed visual projection. Mixed or unknown configuration is refused rather than
reported. The fastfetch subset excludes title, host, local-IP, custom, and object modules; logo
sources cannot be paths. App planning, apply, verification, and rollback are local and do not start
the application or contact a service.

Dependency resolution reads the rice, local environment facts, bundled compatibility data, and the local package database. It does not search remote package indexes. A confirmed install invokes the selected host package manager and may therefore use repositories configured by the user. Alchemy stores a local receipt containing the rice hash, dependency and package identifiers, installed version, provider, trust tier, and timestamp. It does not upload this information.

`alchemy gallery-refresh` is an explicit network action that fetches one static index and stores its ETag, fetch time, and hash locally. Gallery list, detail, search, sorting, and the Qt browser use only that cache and make no per-card API requests. `gallery-report` prints the complete local report and a prefilled GitHub URL; it does not open the browser or upload the report.

`alchemy repo-import` is an explicit network action. It sends the public repository URL and pinned
commit request to GitHub or Codeberg through Git and stores a bounded bare repository in the user's
local cache. It does not upload local configuration, environment facts, imported content, findings,
or the generated draft. Reports omit matched secret values and redact repository paths that contain
detected local identity or path data. The cache may contain source blobs from the public repository;
users should treat it as local source data.

Future network access beyond the gallery snapshot and explicit public-repository import will be tied to a visible user action such as checking for a release when enabled or downloading an approved dependency. Screenshots, rice exports, configuration, package lists, and failure reports will not be uploaded automatically.

`alchemy release-check` reads a local release ledger and repository paths without opening or
fetching evidence URLs. The ledger stores public report links and technical environment labels, not
tester names or contact details. Maintainers must review logs and recordings for identities, local
paths, notifications, and credentials before linking them from the public ledger.

Debug redaction and capture sanitization are safety aids, not guarantees. Review output before posting it publicly.
