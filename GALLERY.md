# Community gallery

Alchemy's gallery is a free metadata index over creator-owned releases. It does not host rice
files or screenshots, rank paid submissions, or execute repository content. The production index
is intended to live in the separate public `alchemy-rice-index` repository; this repository carries
the schemas, validator, deterministic builder, client, and an empty index scaffold.

## Submission contract

A submission is one JSON file in `gallery/entries/` conforming to
`schemas/gallery-entry-v1.schema.json`. It identifies a canonical `.rice` release asset, one through
four screenshots, exact SHA-256 values, compatibility declarations, component and dependency
summaries, SPDX license fields, fixed tags, and publication dates.

Gallery v1 accepts GitHub and Codeberg repositories. The `.rice` file must be a release asset from
the same owner and repository named by `source.repo`. Screenshots must be either release assets or
raw files at the declared full commit. Mutable branch URLs, cross-repository assets, URL credentials,
fragments, embedded content, commands, and arbitrary tags are rejected.

The source repository must contain `.alchemy/manifest.json` at the pinned commit:

```json
{
  "challenge": "alchemy-gallery:github:creator/rice:night",
  "entry_id": "github:creator/rice:night"
}
```

The identifier must exactly match the submitted entry. Because the proof is read from the pinned
creator repository rather than the pull request, a third party cannot claim ownership merely by
copying listing metadata.

## Safe validation

Run a structural validation locally:

```bash
alchemy gallery-validate gallery/entries
```

The index check adds `--verify-remote`. It derives the ownership URL from the repository and commit,
downloads only bounded data from the supported forge, checks the rice and screenshot hashes, parses
the rice as canonical config-only v2 data, compares every projected field, and accepts bounded PNG,
JPEG, or WebP dimensions. It never installs the submitted project, runs hooks, imports contributor
modules, invokes build scripts, or executes content from the rice.

The pull-request workflow checks out the base revision separately and runs that trusted validator
against the contributor checkout as data. Its token is read-only. Changes to validation code must be
reviewed and merged before a submission can depend on them.

Automated checks are not a replacement for moderation. Maintainers may still remove impersonation,
spam, malicious links, abusive text, copyright complaints, compromised sources, and scanner false
positives.

## Static snapshot

The deterministic builder sorts source entries by id, merges only maintainer-owned aggregate
metrics, derives objective badges, and includes a digest over the exact source entries. It does not
add a build clock, so identical inputs produce identical bytes.

```bash
alchemy gallery-build gallery/entries gallery.json --metrics gallery/metrics.json
alchemy gallery-build gallery/entries gallery.json --metrics gallery/metrics.json --check
```

Contributor files cannot set confirmation counts, release download counts, known-breakage records,
or badge labels. Those values come from the trusted metrics file and the builder. Release download
counts are labeled as such and are not described as unique users. Gallery v1 has no star rating.

The supported orderings are New, Recently Updated, Most Downloaded, Community Confirmed, and
Compatible With My System. Compatibility ordering uses declared Plasma, distro, and session data;
it is not a promise that every third-party component will work.

## Offline-first browser

`gallery-refresh` is an explicit network action. It retrieves one static `gallery.json`, validates it
before replacement, and stores its ETag and canonical hash in the owner-only Alchemy data directory.
A `304 Not Modified` response reuses the validated cache. The browser never makes live GitHub API
requests for individual cards.

```bash
alchemy gallery-refresh
alchemy gallery-list --sort updated
alchemy gallery-list --query dark --tag productivity
alchemy gallery-show github:creator/rice:night
alchemy gallery
```

The Qt browser and list/show commands continue to work from the last valid cache while offline. An
empty gallery is shown before the first successful refresh. For testing or air-gapped transfer, a
downloaded snapshot can be imported explicitly:

```bash
alchemy gallery-cache gallery.json --sha256 EXPECTED_HASH
```

The current refresh and report URLs use this repository's public scaffold, so both paths work before
the first community entry exists. They will move to `alchemy-rice-index` when that separate public
repository is published; cached snapshots remain valid because their format and hashes do not depend
on the hosting repository.

## Explicit reports

Reports are generated locally from one cached rice identity and the current Plasma, distro, and
session observation. A failure also requires a bounded component and error class.

```bash
alchemy gallery-report github:creator/rice:night --result success
alchemy gallery-report github:creator/rice:night --result failure \
  --failed-component panels --error-class verification_failed
```

The command prints the complete report and a prefilled GitHub issue URL. It does not open the URL or
upload anything. The user reviews the JSON and chooses whether to open and submit the public form.

## Objective badges

The builder emits only explainable badges: schema valid, pinned source, config-only rice,
official-repository dependencies only, third-party code dependency, exact tested environment,
community-confirmed report count, and exact known-broken Plasma versions. No color score or opaque
risk grade is derived from small samples.
