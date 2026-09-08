# Contributing

Alchemy is early in development. Changes should be small enough to review and should preserve the distinction between domain logic and KDE mutation.

## Development setup

Use Python 3.12 or newer:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
pytest
ruff check .
mypy src
```

Core logic and tests must run without a KDE session. KDE-specific behavior requires a real Plasma 6 test environment; do not add production behavior that fakes a successful KDE operation on another platform.

## Change requirements

- Use type hints in engine code.
- Pass external command arguments as a sequence; never construct a shell command string.
- Keep rice data declarative. Do not add command or executable payload fields.
- Add tests for parsing, planning, mutation, verification, and rollback behavior as applicable.
- Document the exact Plasma version, session, and distro used for integration tests.
- Do not commit personal configuration, generated prompts, planning notes, secrets, or private paths.
- Keep gallery submissions metadata-only and run both deterministic snapshot checks. Gallery CI must
  use trusted validator code and must never install or execute a contributor checkout.

Gallery entry ownership, release, screenshot, license, and hash requirements are documented in
`GALLERY.md`. Structural validation is local; remote verification additionally reads bounded public
bytes from the creator's pinned repository.

KDE APIs and configuration keys change. Link to upstream documentation or source in a pull request when adding a driver, and distinguish documented behavior from an observed workaround.

## Release evidence

Package, VM, hardware, destructive-test, and beta results belong in public issue or CI records
before their URLs are added to `release/evidence-v1.json`. Do not mark a result passed from a mock,
unit test, inferred distro version, or unreviewed local run. Never include tester identity or raw
private logs. `alchemy release-check release/evidence-v1.json --require beta` and `--require launch`
are the authoritative readiness checks; maintainers review the referenced evidence before any
publication decision.
