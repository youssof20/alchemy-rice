# Packaging

No binary, distro package, or beta release is published yet. The repository contains development
packaging for an Arch VCS package and a Debian-family native package, plus standards-based Python
wheel and source-distribution metadata. These paths still require the real distro results tracked
in [RELEASE.md](RELEASE.md).

## Python distributions

Build a wheel and source distribution in an isolated development environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python -m build
python -m twine check dist/*
sha256sum dist/*
```

The wheel installs the `alchemy` command, desktop entry, AppStream metadata, scalable icon, and
versioned compatibility databases. Release artifacts must include published SHA-256 values. They
are not signed until the project has a sustainable signing-key process.

## Arch development package

`packaging/arch/PKGBUILD` is an `alchemy-rice-git` source package. It follows the public repository,
builds a wheel with the system PEP 517 toolchain, runs the test suite, and installs with
`python-installer` rather than invoking pip against the live system.

```bash
mkdir alchemy-rice-package
cp packaging/arch/PKGBUILD alchemy-rice-package/
cd alchemy-rice-package
makepkg --syncdeps --cleanbuild
sudo pacman -U alchemy-rice-git-*.pkg.tar.zst
```

Inspect the PKGBUILD before running it. This is development packaging, not an AUR publication. A
release package must use an immutable release source and real checksum instead of the VCS source.

## Debian-family development package

The `debian/` directory uses debhelper 13 and the PEP 517 pybuild plugin. Its runtime dependencies
name the split PySide6 QtCore, QtGui, QtWidgets, and QtDBus modules plus qasync. From a clean source
checkout with the listed build dependencies installed:

```bash
dpkg-buildpackage --build=binary --unsigned-changes --unsigned-source
sudo apt install ../alchemy-rice_0.1.0~dev0_all.deb
```

The result is not claimed compatible with Kubuntu or KDE neon until their matrix runs pass. Distro
package review may require metadata or dependency adjustments before publication.

## Install/remove smoke evidence

For each native format, preserve a public log that records the exact source commit, clean package
build, package metadata query, install, `alchemy --help`, `alchemy app-list`, read-only
`alchemy inspect`, and removal. Do not publish environment output until `alchemy debug-info` or
equivalent manual review has removed personal data. Add the durable log URL to the release ledger
only after the run completes.

## Distribution policy

Native packages update through their distro package manager. Portable packaging remains a fallback
and is not included until it proves reliable for host configuration, emergency CLI recovery, and
distro dependency integration. Flatpak and Snap are not primary paths because their sandbox model
conflicts with the required host inspection and configuration scope. Alchemy never silently
self-updates and never updates during an apply transaction.
