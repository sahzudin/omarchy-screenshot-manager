# Omarchy Screenshot Manager

A native Omarchy Shell bar plugin for browsing, previewing, copying, and
deleting screenshots taken with `omarchy capture screenshot`.

## Features

- Lists screenshots (newest first) from the configured Pictures directory.
- Shows a live thumbnail and count badge on the bar icon.
- Copies any screenshot to the clipboard as PNG data (`wl-copy -t image/png`).
- Trashes screenshots to the desktop trash after an explicit confirmation
  (recoverable — nothing is permanently deleted).
- **Clear all** button trashes every screenshot (two-step confirm, recoverable).
- Fullscreen preview with `Esc` to close and arrow-key navigation through the
  list.
- Takes a new screenshot right from the bar (right-click) or the panel.
- Opens the screenshots folder in the file manager.
- Text filter to narrow the list by filename or date.
- Auto-refreshes while the panel is open.
- Supports shell IPC (`open`, `close`, `toggle`, `show`, `hide`, and `refresh`).

No privileges are required: screenshots are ordinary user files. Paths are
validated against the screenshots directory, arguments are passed as arrays,
and no shell command strings are evaluated.

## Requirements

- Omarchy with the Quickshell bar (`omarchy.bar`)
- `wl-copy` (wl-clipboard) for clipboard copy
- `gio` (GLib) for trash
- Screenshots taken with `omarchy capture screenshot` (named `screenshot-*.png`
  in `$OMARCHY_SCREENSHOT_DIR`, `$XDG_PICTURES_DIR`, or `~/Pictures`)

## Install

Once this repository has a Git remote:

```bash
omarchy plugin add https://github.com/sahzudin/omarchy-screenshot-manager.git --enable
```

For local development, link the checkout into the user plugin directory and
enable it:

```bash
ln -s ~/Projects/omarchy-screenshot-manager \
      ~/.config/omarchy/plugins/io.github.sahzudin.omarchy-screenshot-manager
omarchy plugin enable io.github.sahzudin.omarchy-screenshot-manager right
```

Saved changes under `~/.config/omarchy/plugins/` reload automatically. If a
change does not apply, force a reload:

```bash
omarchy-shell shell rescanPlugins
```

## Usage

- **Left-click** the camera icon — open the manager panel.
- **Right-click** — take a new screenshot (`omarchy capture screenshot`).
- **Middle-click** — copy the newest screenshot to the clipboard.
- In the panel, each row offers **Preview**, **Copy**, and **Trash**
  (two-step confirm) actions; double-click a row to preview it. The header's
  **Clear all** button trashes every screenshot (two-step confirm).
- `Enter` in the filter box previews the first matching screenshot.

## Configuration

Per-widget settings go in the widget's entry in `~/.config/omarchy/shell.json`
under `bar.layout.<section>`:

```jsonc
{
  "id": "io.github.sahzudin.omarchy-screenshot-manager",
  "icon": "󰄀",        // any Nerd Font glyph; default is md-camera
  "showCount": true   // set false to hide the screenshot count on the bar
}
```

The file hot-reloads on save.

## Remove

Disable the widget, then remove it to restore the previous bar layout:

```bash
omarchy plugin disable io.github.sahzudin.omarchy-screenshot-manager
omarchy plugin remove io.github.sahzudin.omarchy-screenshot-manager
```

Screenshots are never deleted; any trashed files stay in the desktop trash.
Removing the plugin only removes the bar widget.

## License

MIT — see `LICENSE`.