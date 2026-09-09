# Alchemy

Alchemy is a free, GPL-licensed KDE Plasma 6 ricing workbench. It inspects the
current desktop, shows an exact change plan, snapshots affected configuration,
applies reviewed settings, verifies the result, and can restore the previous state.

This is an **alpha test build**. Use a disposable Plasma user account or VM first.
Real-distro testing is beginning now; the package is not yet a public beta.

## Features

- Inspect the Plasma version, session, distro, tools, monitors, portals, and supported settings.
- Plan, apply, verify, and revert reviewed colors, icons, cursors, fonts, styles, decorations,
  wallpaper, selected KWin settings, and semantic panel layouts.
- Import, inspect, export, and combine declarative `.rice` files without executing code from them.
- Capture a sanitized rice draft from supported local settings.
- Resolve optional dependencies with package source and trust information shown before installation.
- Import supported settings from a pinned dotfiles repository without running its scripts.
- Manage reviewed visual settings for Konsole, Kitty, Starship, and fastfetch.
- Browse the local cached gallery and generate a GitHub compatibility-report link.
- Recover interrupted transactions from the durable journal.

## Which distro should I use?

Desktop changes are enabled only on **KDE Plasma 6.6 through 6.8**. Wayland is the primary test
session. Run `plasmashell --version` and `echo "$XDG_SESSION_TYPE"` before installing.

| Distro | Current test status | Setup command below |
| --- | --- | --- |
| Arch Linux | Plasma 6.7 target; best first test choice | Arch |
| CachyOS / EndeavourOS | Arch-family target; not yet verified | Arch |
| Fedora KDE 43 or 44 | Plasma 6.7 target; not yet verified | Fedora |
| Kubuntu 26.04 LTS | Plasma 6.6 target; not yet verified | Debian family |
| KDE neon User Edition | Use only when `plasmashell --version` reports 6.6–6.8 | Debian family |
| Debian 13 | Plasma 6.3: inspect/export only; Apply stays disabled | Debian family |
| Kubuntu 24.04 or 25.10 | Plasma is outside the supported range; do not test Apply | Debian family |
| openSUSE Tumbleweed KDE | Best-effort target; verify Plasma is 6.6–6.8 | openSUSE |

None of these rows is a completed compatibility claim yet. Results are recorded in
[COMPATIBILITY.md](COMPATIBILITY.md).

## Install the alpha test build

The commands below install Python prerequisites. Pick the block for your distro.

### Arch, CachyOS, or EndeavourOS

```bash
sudo pacman -S --needed python python-pip
python -m venv "$HOME/.local/share/alchemy-test"
```

### Fedora KDE

```bash
sudo dnf install python3 python3-pip
python3 -m venv "$HOME/.local/share/alchemy-test"
```

### Debian 13, Kubuntu, or KDE neon

```bash
sudo apt update
sudo apt install python3 python3-venv python3-pip
python3 -m venv "$HOME/.local/share/alchemy-test"
```

### openSUSE Tumbleweed

```bash
sudo zypper install python3 python3-pip
python3 -m venv "$HOME/.local/share/alchemy-test"
```

Then install the same release wheel on any of those systems:

```bash
"$HOME/.local/share/alchemy-test/bin/python" -m pip install --upgrade pip
"$HOME/.local/share/alchemy-test/bin/python" -m pip install \
  https://github.com/youssof20/alchemy-rice/releases/download/v0.1.0a2/alchemy_rice-0.1.0a2-py3-none-any.whl
```

## Run it

Start with read-only commands:

```bash
ALCHEMY="$HOME/.local/share/alchemy-test/bin/alchemy"
"$ALCHEMY" inspect
"$ALCHEMY" list-settings
"$ALCHEMY" app-list
"$ALCHEMY" gui
```

On a disposable Plasma 6.6–6.8 test account, try one complete transaction:

```bash
"$ALCHEMY" plan-color BreezeDark
"$ALCHEMY" apply-color BreezeDark --yes
"$ALCHEMY" revert --last
```

Review the plan before using `--yes`. To inspect recovery state after an interrupted operation:

```bash
"$ALCHEMY" recovery --list
```

## Run from source

```bash
git clone https://github.com/youssof20/alchemy-rice.git
cd alchemy-rice
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
pytest
alchemy inspect
```

## Important limits

- Real Plasma integration results are still pending. Unit tests use controlled fake KDE boundaries.
- Apply is disabled outside Linux, outside Plasma 6.6–6.8, when required KDE tools are missing, or
  when plasma-manager owns the configuration.
- A `.rice` is declarative JSON, not an installer. Alchemy never runs commands stored in a rice or
  executes install scripts from imported repositories.
- Package installation and configuration rollback are separate. Alchemy does not blindly uninstall
  a package when a later configuration operation fails.
- Review debug output, captured rices, logs, and recordings before sharing them.

More detail: [SETTING_REFERENCE.md](SETTING_REFERENCE.md), [RICE_FORMAT.md](RICE_FORMAT.md),
[SECURITY.md](SECURITY.md), [PACKAGING.md](PACKAGING.md), and [RELEASE.md](RELEASE.md).
