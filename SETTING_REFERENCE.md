# Setting reference

Phase 2 exposes one-operation plans through `alchemy plan-setting SETTING VALUE` and confirmed mutation through `alchemy apply-setting SETTING VALUE --yes`. Always review the JSON plan before applying it.

| Setting | Value | KDE state |
| --- | --- | --- |
| `icons.theme` | Installed icon-theme identifier | `kdeglobals`, `Icons/Theme` |
| `cursor.theme` | Installed cursor-theme identifier | `kcminputrc`, `Mouse/cursorTheme` |
| `cursor.size` | Integer from 0 through 512 | `kcminputrc`, `Mouse/cursorSize` |
| `plasma.theme` | Installed Plasma theme identifier | `plasmarc`, `Theme/name` |
| `fonts.general` | KConfig/QFont serialized value | `kdeglobals`, `General/font` |
| `fonts.fixed` | KConfig/QFont serialized value | `kdeglobals`, `General/fixed` |
| `fonts.small` | KConfig/QFont serialized value | `kdeglobals`, `General/smallestReadableFont` |
| `fonts.toolbar` | KConfig/QFont serialized value | `kdeglobals`, `General/toolBarFont` |
| `fonts.menu` | KConfig/QFont serialized value | `kdeglobals`, `General/menuFont` |
| `fonts.window_title` | KConfig/QFont serialized value | `kdeglobals`, `WM/activeFont` |
| `application_style.theme` | Installed Qt style identifier | `kdeglobals`, `KDE/widgetStyle` |
| `decoration.plugin` | Installed KWin decoration plugin identifier | `kwinrc`, `org.kde.kdecoration2/library` |
| `decoration.theme` | Theme understood by the selected decoration plugin | `kwinrc`, `org.kde.kdecoration2/theme` |
| `decoration.border_size` | `None`, `NoSides`, `Tiny`, `Normal`, `Large`, `VeryLarge`, `Huge`, `VeryHuge`, or `Oversized` | `kwinrc`, `org.kde.kdecoration2/BorderSize` |
| `decoration.border_auto` | `true` or `false` | `kwinrc`, `org.kde.kdecoration2/BorderSizeAuto` |
| `kwin.placement` | `Smart`, `Maximizing`, `Random`, `Centered`, `ZeroCornered`, or `UnderMouse` | `kwinrc`, `Windows/Placement` |
| `kwin.borderless_maximized` | `true` or `false` | `kwinrc`, `Windows/BorderlessMaximizedWindows` |
| `wallpaper.image` | Existing local image path | Plasma image-wallpaper state |

Color schemes retain the dedicated `plan-color` and `apply-color` commands for compatibility with Phase 1 journals.

Wallpaper apply preserves the current fill mode and changes every Plasma desktop, matching KDE's official apply tool. Alchemy refuses the plan unless all desktops currently use the same local image, the same supported fill mode, and the `org.kde.image` plugin. Supported fill modes are stretch, preserve-aspect fit, preserve-aspect crop, and pad.

Installed-theme and plugin discovery is not implemented yet. A driver verifies the configured value and refreshes the corresponding desktop component, but real-session integration evidence is still required before release support can be claimed.
