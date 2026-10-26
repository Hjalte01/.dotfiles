# Image picker

**Super+Ctrl+V** opens recent copied images. **Super+Shift+Print** opens recent
screenshots. Run `imagepick` in a terminal, or `imagepick-menu` to open its own
Ghostty window. Screenshots come from `~/Pictures/Screenshots`; copied images
come from the existing `cliphist` image history. Both lists show newest first.

| Key | Action |
| --- | --- |
| Up/Down or `k`/`j` | Browse images with a live preview |
| Tab | Switch between screenshots and copied images |
| `c` | Crop |
| `a` or Enter | Add arrows / edit |
| `d` | Draw freehand |
| `y` | Copy the selected image |
| `r` | Refresh the list |
| `q` or Escape | Close the picker |

Crop and drawing open Satty, a small graphical annotation editor. Drag on the
image to use the selected tool; its toolbar also offers text, shapes, colors,
and undo. Press **Enter** to save a new PNG, copy it to the clipboard, and return
to the picker. Press **Escape** to cancel. Original images stay untouched;
saved edits go to `~/Pictures/Screenshots/Edited`.

```sh
imagepick --source clipboard
imagepick --source screenshots --limit 100
imagepick --screenshots-dir ~/Pictures/Screenshots
imagepick --renderer halfcell
```

The default renderer detects terminal image support. Ghostty shows full image
previews; `--renderer halfcell` provides a text-cell fallback for terminals
without image graphics. The picker needs the local Wayland session to use the
clipboard or open Satty. It shows image history only; the existing **Super+V**
clipboard menu still includes text.

The package and shortcuts live in the desktop Home Manager configuration.
After changes, run `nxb` to build and activate them.
