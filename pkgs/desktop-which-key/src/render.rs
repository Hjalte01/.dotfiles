use crate::model::{Binding, Mode, Ui};
use fontdue::{Font, FontSettings, Metrics};
use image::{Rgba, RgbaImage};
use std::collections::HashMap;

pub struct Renderer {
    font: Font,
    glyphs: HashMap<(char, u32), (Metrics, Vec<u8>)>,
}
include!(env!("DOTFILES_THEME_RS"));
impl Renderer {
    pub fn new() -> Self {
        Self {
            font: Font::from_bytes(
                include_bytes!(env!("WHICH_KEY_FONT")) as &[u8],
                FontSettings::default(),
            )
            .unwrap(),
            glyphs: HashMap::new(),
        }
    }
    fn rect(image: &mut RgbaImage, x: u32, y: u32, w: u32, h: u32, color: [u8; 3]) {
        for yy in y..(y + h).min(image.height()) {
            for xx in x..(x + w).min(image.width()) {
                image.put_pixel(xx, yy, Rgba([color[0], color[1], color[2], 255]));
            }
        }
    }
    fn text(
        &mut self,
        image: &mut RgbaImage,
        x: u32,
        y: u32,
        size: u32,
        text: &str,
        color: [u8; 3],
        max: u32,
    ) {
        let mut cursor = x as f32;
        for ch in text.chars() {
            let (m, bitmap) = self
                .glyphs
                .entry((ch, size))
                .or_insert_with(|| self.font.rasterize(ch, size as f32));
            if cursor + m.advance_width > (x + max) as f32 {
                break;
            }
            let top = y as i32 + size as i32 - m.height as i32 - m.ymin;
            for yy in 0..m.height {
                for xx in 0..m.width {
                    let px = cursor as i32 + m.xmin + xx as i32;
                    let py = top + yy as i32;
                    if px < 0 || py < 0 || px >= image.width() as i32 || py >= image.height() as i32
                    {
                        continue;
                    }
                    let alpha = bitmap[yy * m.width + xx] as u32;
                    let dst = image.get_pixel_mut(px as u32, py as u32);
                    for c in 0..3 {
                        dst[c] =
                            ((color[c] as u32 * alpha + dst[c] as u32 * (255 - alpha)) / 255) as u8;
                    }
                }
            }
            cursor += m.advance_width;
        }
    }
    pub fn draw(
        &mut self,
        ui: &mut Ui,
        bindings: &[Binding],
        w: u32,
        h: u32,
        scale: u32,
    ) -> RgbaImage {
        let theme = desktop_theme::palette();
        let mut image = RgbaImage::from_pixel(w * scale, h * scale, Rgba([theme.base[0], theme.base[1], theme.base[2], 255]));
        // Lay out in logical pixels and rasterize glyphs at the buffer scale.
        let s = scale;
        Self::rect(&mut image, 0, 0, w * s, 2 * s, theme.accent);
        let title = match &ui.mode {
            Mode::Peek => "Super · common shortcuts".into(),
            Mode::Context(name) => format!("{} · choose your next key", name.to_uppercase()),
            _ => "Your key map".into(),
        };
        self.text(
            &mut image,
            24 * s,
            18 * s,
            24 * s,
            &title,
            theme.text,
            (w - 48) * s,
        );
        let subtitle = if ui.mode == Mode::Pinned {
            if ui.search {
                "/ Search keys or descriptions     F1 Help     Tab Browse     Esc Back / close"
            } else {
                "/ Search keys or descriptions     ? Help     Tab Search     Esc Close"
            }
        } else if matches!(ui.mode, Mode::Context(_)) {
            "Press a listed key · Esc or an unknown key cancels · Super+Esc pins the searchable map"
        } else {
            "Release Super to hide · Group keys work with Super held or released · Super+Esc pins ALL bindings"
        };
        self.text(
            &mut image,
            24 * s,
            53 * s,
            13 * s,
            subtitle,
            theme.muted,
            (w - 48) * s,
        );
        if ui.help {
            let lines = [
                "Find your way",
                "",
                "Hold Super: peek after 250 ms; release to dismiss.",
                "Super+Esc / Super+M / F9: pin or close this map.",
                "/ or Ctrl+F: search ALL keys and descriptions, including sequences.",
                "Search is case-insensitive; separate words narrow the matches.",
                "Tab: switch between typing a search and browsing the results.",
                "Up / Down: select · Page Up / Down: page · Home / End: first / last.",
                "Enter: run the selected action (mouse/release gestures are reference only).",
                "Ctrl+U: clear search · ?: help while browsing · F1: help at any time.",
                "Esc: leave help, then clear search, then close the map.",
                "",
                "Groups: Super+G websites · Super+A audio · Super+X pointer tools",
                "Super+T desktop controls · Super+C Codex · Super+S system power",
                "",
                "Common shortcuts keep working in peek and sequence views.",
                "The pinned map owns typing; close it to use normal desktop shortcuts.",
            ];
            for (i, line) in lines.iter().enumerate() {
                self.text(
                    &mut image,
                    28 * s,
                    (94 + i as u32 * 27) * s,
                    16 * s,
                    line,
                    if i == 0 { theme.accent } else { theme.text },
                    (w - 56) * s,
                );
            }
            return image;
        }
        let rows = ui.filtered(bindings);
        ui.selected = ui.selected.min(rows.len().saturating_sub(1));
        let context = matches!(ui.mode, Mode::Context(_));
        let columns = if context { 2 } else { (w / 430).clamp(1, 4) };
        let row_height = 52;
        let per_column = (h.saturating_sub(190) / row_height).max(1) as usize;
        ui.page_size = per_column * columns as usize;
        let page = ui.selected / ui.page_size;
        let start = page * ui.page_size;
        let search = if ui.query.is_empty() {
            if ui.search {
                "Type to search all bindings…".into()
            } else {
                format!("{} bindings · grouped by purpose", rows.len())
            }
        } else {
            format!(
                "/ {}  ·  {} matches{}",
                ui.query,
                rows.len(),
                if ui.search {
                    " · typing"
                } else {
                    " · browsing"
                }
            )
        };
        Self::rect(
            &mut image,
            20 * s,
            82 * s,
            (w - 40) * s,
            34 * s,
            theme.surface,
        );
        self.text(
            &mut image,
            30 * s,
            88 * s,
            15 * s,
            &search,
            theme.accent,
            (w - 60) * s,
        );
        let col_width = (w - 40) / columns;
        for (offset, entry) in rows.iter().skip(start).take(ui.page_size).enumerate() {
            let col = offset / per_column;
            let row = offset % per_column;
            let x = 20 + col as u32 * col_width;
            let y = 128 + row as u32 * row_height;
            let selected = start + offset == ui.selected && ui.mode == Mode::Pinned;
            if selected {
                Self::rect(
                    &mut image,
                    x * s,
                    y * s,
                    (col_width - 10) * s,
                    49 * s,
                    theme.overlay,
                );
            }
            let combo = if context {
                entry.combo.split(" → ").last().unwrap_or(&entry.combo)
            } else {
                &entry.combo
            };
            self.text(
                &mut image,
                (x + 9) * s,
                (y + 3) * s,
                15 * s,
                combo,
                theme.accent,
                (col_width - 24) * s,
            );
            let group_label = entry
                .group
                .strip_prefix("Sequences · ")
                .unwrap_or(&entry.group);
            self.text(
                &mut image,
                (x + col_width - 173) * s,
                (y + 5) * s,
                9 * s,
                group_label,
                theme.muted,
                157 * s,
            );
            self.text(
                &mut image,
                (x + 9) * s,
                (y + 24) * s,
                14 * s,
                &entry.description,
                theme.text,
                (col_width - 24) * s,
            );
        }
        if rows.is_empty() {
            self.text(
                &mut image,
                30 * s,
                144 * s,
                18 * s,
                "No matches. Ctrl+U clears the search.",
                theme.muted,
                (w - 60) * s,
            );
        }
        let foot = if !ui.error.is_empty() {
            ui.error.clone()
        } else if matches!(ui.mode, Mode::Context(_)) {
            "Choose a listed key · Super may remain held · Esc cancels".into()
        } else if ui.mode == Mode::Peek {
            "Common shortcuts · Super+Esc opens every modifier shortcut and sequence · Release Super to hide".into()
        } else if let Some(entry) = rows.get(ui.selected) {
            format!(
                "{} · {}   |   Page {}/{} · ↑↓ select · PgUp/PgDn browse · Enter run",
                entry.group,
                entry.description,
                page + 1,
                rows.len().div_ceil(ui.page_size).max(1)
            )
        } else {
            "Esc to close".into()
        };
        Self::rect(
            &mut image,
            20 * s,
            (h - 44) * s,
            (w - 40) * s,
            1 * s,
            theme.overlay,
        );
        self.text(
            &mut image,
            24 * s,
            (h - 32) * s,
            12 * s,
            &foot,
            theme.muted,
            (w - 48) * s,
        );
        image
    }
}
