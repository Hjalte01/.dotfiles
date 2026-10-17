include!(env!("DOTFILES_THEME_RS"));
use crate::{
    audio::BANDS,
    pipeline::{Controller, Phase, Shared, View, lock},
};
use anyhow::{Context, Result};
use gtk::{glib, prelude::*};
use gtk_layer_shell::{Edge, KeyboardMode, Layer, LayerShell};
use std::{
    cell::RefCell,
    rc::Rc,
    sync::{Arc, mpsc::Receiver},
    time::{Duration, Instant},
};

pub fn run(shared: Arc<Shared>, commands: Option<Receiver<String>>, demo: bool) -> Result<()> {
    gtk::init().context("Could not connect to the desktop")?;
    anyhow::ensure!(
        gtk_layer_shell::is_supported(),
        "This overlay requires a Wayland desktop with layer-shell"
    );
    let window = gtk::Window::new(gtk::WindowType::Toplevel);
    window.set_title("Dictation");
    window.set_decorated(false);
    window.set_resizable(false);
    window.set_accept_focus(false);
    window.set_focus_on_map(false);
    window.set_skip_taskbar_hint(true);
    window.set_skip_pager_hint(true);
    window.set_app_paintable(true);
    if let Some(visual) = GtkWindowExt::screen(&window).and_then(|screen| screen.rgba_visual()) {
        window.set_visual(Some(&visual));
    }
    window.init_layer_shell();
    window.set_namespace("dictation-live");
    window.set_layer(Layer::Overlay);
    window.set_anchor(Edge::Bottom, true);
    window.set_layer_shell_margin(Edge::Bottom, 28);
    window.set_keyboard_mode(KeyboardMode::None);
    window.set_exclusive_zone(0);
    // Both keyboard and pointer input pass through to the original application.
    window.connect_realize(|window| {
        if let Some(native) = window.window() {
            native.input_shape_combine_region(&gtk::cairo::Region::create(), 0, 0);
        }
    });
    let css = gtk::CssProvider::new();
    css.load_from_data(
        b"
        window { background: transparent; }
        .dictation-card { background: #111b29; color: #e8eef8; border: 1px solid #375068;
          border-radius: 14px; padding: 13px 16px; }
        .dictation-status { font-weight: bold; font-size: 12px; color: #7dd3fc; }
        .dictation-text { font-size: 14px; color: #f1f5f9; }
        .dictation-detail { font-size: 10px; color: #9badc3; }
    ",
    )?;
    let mut theme_css = String::new();
    if let Ok(value) = std::fs::read_to_string(desktop_theme::config("dictation.css")) {
        css.load_from_data(value.as_bytes())?;
        theme_css = value;
    }
    let live_css = css.clone();
    glib::timeout_add_local(Duration::from_millis(100), move || {
        if let Ok(value) = std::fs::read_to_string(desktop_theme::config("dictation.css")) {
            if value != theme_css && live_css.load_from_data(value.as_bytes()).is_ok() {
                theme_css = value;
            }
        }
        glib::ControlFlow::Continue
    });
    gtk::StyleContext::add_provider_for_screen(
        &GtkWindowExt::screen(&window).context("No screen")?,
        &css,
        gtk::STYLE_PROVIDER_PRIORITY_APPLICATION,
    );
    let card = gtk::Box::new(gtk::Orientation::Vertical, 8);
    card.style_context().add_class("dictation-card");
    card.set_width_request(440);
    let header = gtk::Box::new(gtk::Orientation::Horizontal, 12);
    let status = gtk::Label::new(Some("● Listening"));
    status.style_context().add_class("dictation-status");
    status.set_xalign(0.0);
    header.pack_start(&status, true, true, 0);
    let timer = gtk::Label::new(Some("0:00"));
    timer.style_context().add_class("dictation-detail");
    header.pack_end(&timer, false, false, 0);
    card.pack_start(&header, false, false, 0);
    let text = gtk::Label::new(Some("Speak in English or Danish…"));
    text.style_context().add_class("dictation-text");
    text.set_xalign(0.0);
    text.set_yalign(1.0);
    text.set_line_wrap(true);
    text.set_line_wrap_mode(gtk::pango::WrapMode::WordChar);
    text.set_ellipsize(gtk::pango::EllipsizeMode::Start);
    text.set_lines(4);
    text.set_max_width_chars(56);
    text.set_height_request(66);
    card.pack_start(&text, true, true, 0);
    let graph = gtk::DrawingArea::new();
    graph.set_height_request(37);
    let graph_view = Arc::clone(&shared);
    graph.connect_draw(move |area, context| {
        let view = lock(&graph_view.view);
        let width = area.allocated_width() as f64;
        let height = area.allocated_height() as f64;
        let step = width / BANDS as f64;
        for (index, level) in view.bands.iter().enumerate() {
            let value = if view.phase == Phase::Listening {
                *level as f64
            } else {
                0.0
            };
            let bar = (height * value).max(2.0);
            let accent = desktop_theme::palette().accent;
            context.set_source_rgba(accent[0] as f64 / 255., accent[1] as f64 / 255., accent[2] as f64 / 255., 0.95);
            context.rectangle(index as f64 * step, height - bar, step - 3.0, bar);
            let _ = context.fill();
        }
        glib::Propagation::Proceed
    });
    card.pack_start(&graph, false, false, 0);
    let details = gtk::Box::new(gtk::Orientation::Horizontal, 8);
    let frequency = gtk::Label::new(Some("80 Hz                         8 kHz"));
    frequency.style_context().add_class("dictation-detail");
    details.pack_start(&frequency, true, true, 0);
    let level = gtk::Label::new(Some("−∞ dBFS"));
    level.style_context().add_class("dictation-detail");
    details.pack_end(&level, false, false, 0);
    card.pack_start(&details, false, false, 0);
    let hint = gtk::Label::new(Some("F11 / Super+D: stop     Super+Alt+Esc: cancel"));
    hint.style_context().add_class("dictation-detail");
    hint.set_xalign(0.0);
    card.pack_start(&hint, false, false, 0);
    window.add(&card);
    let controller = Rc::new(RefCell::new(Controller::new(Arc::clone(&shared))));
    let last_text = Rc::new(RefCell::new(String::new()));
    if demo {
        let mut view = lock(&shared.view);
        *view = View {
            phase: Phase::Listening,
            status: "Demo · microphone off".into(),
            ready: true,
            ..View::default()
        };
    }
    let demo_start = Instant::now();
    glib::timeout_add_local(Duration::from_millis(32), move || {
        if let Some(commands) = &commands {
            for command in commands.try_iter() {
                let result = match command.as_str() {
                    "toggle" => controller.borrow_mut().toggle(),
                    "cancel" => {
                        controller.borrow_mut().cancel();
                        Ok(())
                    }
                    value if value.starts_with("replay\t") => controller
                        .borrow_mut()
                        .replay(std::path::Path::new(&value[7..])),
                    _ => Ok(()),
                };
                if let Err(error) = result {
                    shared.error(format!("{error:#}"));
                }
            }
        }
        controller.borrow_mut().poll();
        if demo {
            let elapsed = demo_start.elapsed().as_secs_f32();
            let mut view = lock(&shared.view);
            view.text = [
                "",
                "Vi bruger DDPM",
                "Vi bruger DDPM og iMF.",
                "Vi bruger DDPM og iMF. Live text appears here as you speak.",
            ][(elapsed / 1.1) as usize % 4]
                .into();
            for (i, bar) in view.bands.iter_mut().enumerate() {
                *bar = ((elapsed * 5.0 + i as f32 * 0.6).sin() * 0.3 + 0.4).max(0.0);
            }
            view.db = -20.0;
            if elapsed >= 9.0 {
                gtk::main_quit();
                return glib::ControlFlow::Break;
            }
        }
        let mut view = lock(&shared.view);
        if view
            .hide_at
            .is_some_and(|deadline| Instant::now() >= deadline)
        {
            view.phase = Phase::Hidden;
            view.hide_at = None;
        }
        if view.phase == Phase::Hidden {
            window.hide();
        } else {
            let prefix = match view.phase {
                Phase::Listening => "●",
                Phase::Error => "!",
                Phase::Done => "✓",
                _ => "◌",
            };
            status.set_text(&format!("{prefix} {}", view.status));
            let elapsed = view.started.elapsed().as_secs();
            timer.set_text(&format!("{}:{:02}", elapsed / 60, elapsed % 60));
            let display = if view.text.is_empty() {
                "Speak in English or Danish…"
            } else {
                &view.text
            };
            if *last_text.borrow() != display {
                text.set_text(display);
                *last_text.borrow_mut() = display.to_owned();
            }
            level.set_text(&format!("{:.0} dBFS", view.db));
            graph.queue_draw();
            if !window.is_visible() {
                window.show_all();
            }
        }
        glib::ControlFlow::Continue
    });
    gtk::main();
    Ok(())
}
