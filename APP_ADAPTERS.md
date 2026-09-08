# Application adapters

Alchemy supports versioned visual subsets for Konsole, Kitty, Starship, and fastfetch. An adapter
does not copy an application's complete configuration. It owns one documented file, refuses an
existing file containing fields outside its allowlist, and writes only after a token-bound preview.

```bash
alchemy app-list
alchemy app-inspect kitty
alchemy plan-app kitty examples/apps/kitty.json
alchemy apply-app kitty examples/apps/kitty.json --plan-token TOKEN_FROM_PLAN --yes
alchemy revert --last
```

`plan-app` requires the application executable, an eligible KDE Plasma environment, and adapter
format 1 JSON. It shows the target file and a confirmation token bound to the current supported
state, requested settings, and path. `apply-app` recomputes the plan under the shared mutation lock;
if either file changed, the old token is rejected. Apply snapshots the target, journals the state,
writes atomically, parses the resulting file, and compares it with the plan. Revert restores the
previous supported settings or removes a file that did not previously exist.

Adapters never start or reload an application. File verification confirms the persistent config,
not the appearance of an already running window. The user controls when to start or reload the app.

## Owned files and visual fields

| Adapter | Complete owned file | Format 1 visual fields |
| --- | --- | --- |
| Konsole | `$XDG_DATA_HOME/konsole/Alchemy.profile` | color scheme name, font family/size, bold-intense text, line spacing, cursor shape |
| Kitty | `$XDG_CONFIG_HOME/kitty/kitty.conf` | font family/size, foreground/background/cursor colors, cursor shape, opacity, 16 ANSI colors |
| Starship | `$XDG_CONFIG_HOME/starship.toml` | prompt newline, safe built-in module order, fixed character glyph/color, directory and Git-branch colors, named RGB palette |
| fastfetch | `$XDG_CONFIG_HOME/fastfetch/config.jsonc` | built-in text logo, separator, display colors, bright-color flag, privacy-reviewed module list |

The Konsole adapter creates or manages a profile named `Alchemy`; it does not change the default
profile or modify a user's other profiles. Select the profile in Konsole after apply. Its color
scheme must already be installed or declared as a separate pinned dependency.

Kitty's root config can contain includes, generated includes, environment expansion, keyboard
actions, shell integration, and other behavior. For that reason, the adapter refuses any existing
key outside its visual allowlist instead of preserving and reloading a mixed file.

Starship's arbitrary `custom` modules can run commands. The adapter never accepts them. Its module
order is restricted to built-in presentation modules and omits username, hostname, cloud-account,
and local-IP modules. Palette entries are RGB colors, not arbitrary style strings.

fastfetch object modules can include custom formatting or commands and its default title can expose
the username and hostname. The adapter accepts only simple module names from its privacy-reviewed
list and deliberately rejects `title`, `host`, and `localip`. Logo sources are built-in identifiers;
file paths, raw logo data, and image backends are not supported.

## Repository conversion

The repository importer maps the same subsets from Konsole `.profile`, `kitty.conf`,
`starship.toml`, and fastfetch `config.json`/`config.jsonc` files. Unsupported and non-visual fields
are counted but not copied. Multiple different configs for the same app create a blocking conflict
instead of choosing one by path order. The generated rice still requires separate executable,
version, source, and license review.

Alacritty, Ghostty, and Kvantum remain recognized-only until equally conservative ownership and
rollback rules are implemented. Format 1 is the first and only supported adapter schema, so its
migration rule is identity validation from version 1 to version 1 and explicit refusal of every
other version. A future schema must add a reviewed, tested migration before its version is accepted.
