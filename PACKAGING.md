# Packaging

No binary or distro package is published yet.

The current source-development path is:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
```

Packaging is planned after core apply/revert behavior is exercised on real Plasma systems. The intended order is an Arch package/source PKGBUILD, a viable portable build, Fedora packaging, Debian packaging for Kubuntu/KDE neon, and openSUSE packaging.

Flatpak and Snap are not planned as the primary distribution path because Alchemy must inspect and modify host desktop configuration and may coordinate host package dependencies. Native package installations will update through the distro package manager; portable builds will not silently self-update.
