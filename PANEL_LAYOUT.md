# Panel layouts

Phase 3 introduced a dedicated, strict JSON document for Plasma panels. Rice v2 reuses the same panel declarations inside its `components.panels` object; the standalone file retains `format_version` for direct panel planning.

```json
{
  "format_version": 1,
  "panels": [
    {
      "logical_id": "main",
      "location": "bottom",
      "alignment": "center",
      "floating": true,
      "height": {
        "unit": "screen_percent",
        "value": 4.0,
        "min_px": 32,
        "max_px": 64
      },
      "screen_role": "primary",
      "length_mode": "fill",
      "hiding": "none",
      "opacity": "adaptive",
      "widgets": [
        {"plugin": "org.kde.plasma.kickoff", "slot": "left"},
        {"plugin": "org.kde.plasma.icontasks", "slot": "center"},
        {"plugin": "org.kde.plasma.digitalclock", "slot": "right"}
      ]
    }
  ]
}
```

Unknown fields are rejected. A layout is limited to 16 panels, 64 widgets per panel, 128 widgets overall, and 256 KiB of UTF-8 JSON. Plugin identifiers are data only and must use Plasma's identifier character set; commands, widget configuration, and explicit spacer widgets are not accepted.

## Screen and size semantics

`screen_role` is either `primary` or `all`. Plasma screen index 0 is treated as primary; `all` expands one panel onto every observed screen. Connector names and transient numeric IDs are never persisted as portable intent. The preview reports the exact numeric mapping and geometry used for the current session.

Dimensions use `pixels` or `screen_percent`. Panel height percentage is calculated from screen height for top/bottom panels and screen width for left/right panels. `min_px` and `max_px` clamps are applied after conversion. A custom panel length requires a separate `length` dimension and is calculated along the panel's axis.

`location` accepts `top`, `bottom`, `left`, or `right`. `alignment` accepts `left`, `center`, or `right`; `length_mode` accepts `fill`, `fit`, or `custom`; `hiding` accepts `none`, `autohide`, `dodgewindows`, or `windowsgobelow`; and `opacity` accepts `adaptive`, `opaque`, or `translucent`.

## Widget slots and dependencies

Widgets retain their order within the `left`, `center`, and `right` slots. Alchemy compiles these slots into Plasma's ordered applet list and inserts expanding `org.kde.plasma.panelspacer` widgets where separation is needed. Authors cannot declare spacers directly.

Every compiled widget plugin must already be present in Plasma's `knownWidgetTypes`, including generated spacers. A missing third-party widget causes planning to stop with the exact missing plugin identifiers. Alchemy does not insert substitutes or embed executable plasmoid code.

## Preview, apply, and rollback

Run `alchemy inspect-panels` to view the semantic current state. `alchemy plan-panels FILE` displays the current public structure, resolved sizes, widget order, and complete screen mapping. It also emits a confirmation token derived from the captured current state and resolved result.

Apply with `alchemy apply-panels FILE --plan-token TOKEN --yes`. Alchemy captures and checks the state again while holding the mutation lock. If either the current panels or display mapping changed after preview, the token no longer matches and apply stops before mutation.

Apply uses Plasma's scripting API. It creates and configures the complete replacement set before removing the old panels, then captures Plasma's resulting structure for verification. A failed verification triggers a scripted reconstruction of the pre-state, including supported panel and widget configuration groups. Plasma's own serializer excludes transient IDs and internal ordering keys. A targeted file snapshot remains a secondary recovery artifact; the broad `plasma-org.kde.plasma.desktop-appletsrc` file is never overwritten during normal panel apply or rollback.
