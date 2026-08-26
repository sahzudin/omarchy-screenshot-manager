# Omarchy Screenshot Manager — Implementation Plan

A native Omarchy Shell **bar-widget** plugin for browsing, previewing, copying,
and deleting screenshots taken with `omarchy capture screenshot`.

Pattern: the existing `io.github.sahzudin.omarchy-snapshot-manager` plugin
(Quickshell `bar-widget`: `BarWidget.qml` + `Panel.qml` + `Model.js` + helper
script + `manifest.json`).

## 1. Plugin identity & location

| Field | Value |
|---|---|
| id | `io.github.sahzudin.omarchy-screenshot-manager` |
| kinds | `["bar-widget"]` |
| entry point | `BarWidget.qml` |
| bar section | `right` (next to `io.github.sahzudin.omagent-sessions`) |
| source dir | `/home/sahzudin/Projects/omarchy-screenshot-manager/` |
| dev install | symlink/copy into `~/.config/omarchy/plugins/<id>/` (hot-reloads on save) |

Files:
```
manifest.json        # plugin manifest
BarWidget.qml        # bar button: icon + count badge; left/right/middle clicks
Panel.qml            # popup: header, search, thumbnail list, fullscreen preview
Model.js             # normalization/formatting helpers (.pragma library)
screenshotctl.py     # unprivileged helper: list / trash / copy
LICENSE              # MIT (match existing plugins)
README.md            # docs
PLAN.md              # this file
```

## 2. Data source & helper contract

Screenshots are `screenshot-*.png` files written by `omarchy capture screenshot`
to `$OMARCHY_SCREENSHOT_DIR`, `$XDG_PICTURES_DIR`, or `~/Pictures` (in that
order — mirror the lookup in `omarchy-capture-screenshot`).

`screenshotctl.py` subcommands (unprivileged; no pkexec needed — these are
user-owned files):

| Command | Behaviour | JSON out |
|---|---|---|
| `list` | Glob `screenshot-*.png` in the screenshots dir (non-recursive), stat name/size/mtime, newest first, cap at N (e.g. 200) | `{dir, dirName, count, screenshots:[{path,name,size,mtimeIso,humanSize}]}` |
| `trash <path>` | Validate path is inside screenshots dir + matches naming, then `gio trash` (recoverable) | `{trashed:{path}}` |
| `copy <path>` | `wl-copy -t image/png` reading the file (no shell string eval) | `{copied:{path}}` |

Security (mirror snapshot-manager): paths are validated against the screenshots
dir and `^screenshot-.*\.png$` in the helper, args passed as arrays, no shell
command strings. `copy` runs `wl-copy`, which works because the shell is a
Wayland client.

## 3. Bar widget (`BarWidget.qml`)

Reuses `WidgetButton`, `Loader` panel, `IpcHandler` pattern from
`omarchy-snapshot-manager`.

- Label: `Model.barLabel(count, vertical, known)` — camera icon + count badge.
- Tooltip: "N screenshots · left: manage · right: new · middle: copy latest".
- Clicks (via `onPressed(buttonCode)`):
  - **Left** — toggle panel (open + refresh).
  - **Right** — run `omarchy capture screenshot` (smart region flow) via
    `Quickshell.execDetached`; refresh list afterwards.
  - **Middle** — copy newest screenshot to clipboard (status toast in panel).
- `IpcHandler` target `<id>`: `open`, `close`, `toggle`, `show`, `hide`, `refresh`.
- No `pkexec` anywhere.

## 4. Panel (`Panel.qml`)

Follows snapshot-manager structure: `Panel` root + `KeyboardPanel` + `PanelKeyCatcher`
+ `Column`. Uses `qs.Commons` / `qs.Ui` components (`Button`, `TextField`,
`PanelActionButton`, `PanelSeparator`, `Style.space`, `Style.controlFill`, `Color.*`).

Layout top→bottom:

1. **Header row** — icon, title "Screenshot Manager", status line
   (dir name + count / "No screenshots yet" / working / error), action buttons:
   - **Refresh** (`󰑐`) — rerun `list`.
   - **Take screenshot** (`󰁍`) — `omarchy capture screenshot` (region flow).
   - **Open folder** (`󰉋`) — `xdg-open` the screenshots dir.
2. **Search box** — `TextField` filtering rows client-side by filename/mtime.
3. **List** — `ListView`, one row per screenshot:
   - Thumbnail: `Image { source: "file://" + path }` in a fixed box, letterboxed
     (`fillMode: Image.PreserveAspectFit`, dimmed `Color.background`).
   - Name (elided) + meta line (`Model.screenshotMeta`: date + human size).
   - Row actions:
     - **Preview** (`󰋼`) — opens fullscreen preview overlay for that file.
     - **Copy** (`󰅌`) — `copy <path>` via `Process`.
     - **Trash** (`󰭸`) — confirm-then-trash (two-step, 8s timeout timer, like
       snapshot-manager delete). Button text flips `Trash → Confirm`.
   - Enter/double-click on a row also opens the fullscreen preview.
4. **Footer hint** — "Screenshots are copied to the clipboard as PNG · Trash is
   recoverable from the desktop trash."

State/status pattern copied from snapshot-manager:
`statusText`, per-action error strings, `busy` = any `Process.running`, three
`Process` objects (list/trash/copy) with `StdioCollector` + `onExited`.

### Fullscreen preview

A dedicated `PreviewOverlay.qml` mounted inside `Panel.qml` as an always-loaded
`Loader` (or a `LayerWindow` toggled by the panel). Renders a large
`Image` with `fillMode: PreserveAspectFit` centered on the screen:

- **Esc** closes; **←/→** step through the list; **Enter** closes; click/drag
  pans is out of scope v1 (keep it simple).
- Uses `Style`/`Color` theme values for scrim + border so it matches the shell.
- Shows filename + resolution + size caption bar.

Note on manifest: the preview lives *inside* the bar-widget plugin (loaded from
`Panel.qml`), so `kinds` stays `["bar-widget"]` and no second entry point is
needed — avoids the extra `overlay` kind + `keepLoaded` wiring.

## 5. Auto-refresh

- Panel refreshes on `open()` (like snapshot-manager).
- While open, a `Timer` (e.g. 5s) re-runs `list` if a change is suspected —
  simplest reliable trigger: poll `list` at a modest interval only while the
  panel is open; on success, swap rows in place without closing the panel.
- Bar badge count updates from the same state.

## 6. Enabling / install

```bash
# dev: symlink into the user plugin dir (hot-reload on save)
ln -s ~/Projects/omarchy-screenshot-manager \
      ~/.config/omarchy/plugins/io.github.sahzudin.omarchy-screenshot-manager

# validate manifest against the schema
omarchy plugin validate ~/Projects/omarchy-screenshot-manager

# add to the bar (right section, after omagent-sessions)
# edit ~/.config/omarchy/shell.json -> bar.layout.right[] += {"id":"io.github.sahzudin.omarchy-screenshot-manager"}
omarchy plugin list        # confirm discovery
omarchy restart shell      # if hot-reload doesn't pick it up
```

Ship as git repo: `omarchy plugin add https://github.com/sahzudin/omarchy-screenshot-manager.git --enable`.

## 7. Out of scope (v1)

- Video recordings, non-`screenshot-*` images, subdirectory scanning.
- Editing/annotating images (that's `tensaku-edit` via the capture flow).
- OCR text extraction (that's `omarchy capture text`).
- Persisting sort/filter preferences.
- Grid view / multi-select bulk trash.
- Drag-and-drop reorder.

## 8. Build order

1. `manifest.json` + `LICENSE` + `screenshotctl.py` (validated standalone).
2. `Model.js` (parse/normalize/format, mirrors snapshot-manager).
3. `BarWidget.qml` (button + IPC + panel loader).
4. `Panel.qml` (header, search, list w/ thumbnails, actions).
5. `PreviewOverlay.qml` (fullscreen preview + keyboard nav).
6. Symlink + `plugin validate` + shell.json layout entry + restart shell.
7. Manual QA: take a screenshot, verify list/thumbnails/copy-paste/trash/preview/search/open-folder/middle-click-copy.
8. `README.md`; optional git init + commit.

## 9. Acceptance criteria

- Bar icon shows a live count of screenshots.
- Left-click opens the panel listing newest-first with thumbnails.
- Copy puts a real image on the clipboard (paste into an app works).
- Trash is two-step-confirm and lands in the trash (recoverable).
- Enter/double-click shows a fullscreen preview; Esc/arrows behave.
- Right-click takes a new screenshot; the list refreshes automatically.
- Search filters rows by filename/date.
- `omarchy plugin validate` passes; no shell-string evaluation anywhere.