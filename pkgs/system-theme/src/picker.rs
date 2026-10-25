use crate::engine::{Engine, Lock};
use anyhow::{Context, Result};
use gtk::{gdk, glib, prelude::*};
use gtk_layer_shell::{KeyboardMode, Layer, LayerShell};
use serde_json::{json, Value};
use std::{
    cell::{Cell, RefCell},
    path::PathBuf,
    rc::Rc,
    sync::{
        atomic::{AtomicBool, Ordering},
        mpsc,
    },
    thread,
    time::{Duration, Instant},
};

static INTERRUPTED: AtomicBool = AtomicBool::new(false);
extern "C" fn interrupt(_: i32) {
    INTERRUPTED.store(true, Ordering::Relaxed);
}

#[derive(Clone)]
struct Choice {
    label: String,
    state: Value,
    image: PathBuf,
    palette: Value,
}
enum Request {
    Preview(Value),
    Commit(Value),
    Cancel,
}
enum Reply {
    Applied(f64),
    Done(Option<String>),
}

fn choices(engine: &Engine, saved: &Value, walls: bool) -> Result<Vec<Choice>> {
    let mut result = Vec::new();
    if walls {
        let key = saved["theme"].as_str().unwrap_or("mocha");
        for (wall, label) in &engine.wallpapers {
            let mut state = saved.clone();
            state["wallpapers"][key] = json!(wall);
            result.push(Choice {
                label: label.clone(),
                image: engine.catalog.join(key).join(format!("{wall}-thumb.png")),
                state,
                palette: engine.palette(key)?.clone(),
            });
        }
        fn images(root: &std::path::Path, files: &mut Vec<PathBuf>, depth: usize) {
            if depth > 8 {
                return;
            }
            if let Ok(entries) = std::fs::read_dir(root) {
                for entry in entries.flatten() {
                    let path = entry.path();
                    if entry.file_type().is_ok_and(|t| t.is_dir()) {
                        images(&path, files, depth + 1);
                    } else if path.extension().and_then(|s| s.to_str()).is_some_and(|s| {
                        ["png", "jpg", "jpeg", "webp"].contains(&s.to_lowercase().as_str())
                    }) {
                        files.push(path);
                    }
                }
            }
        }
        let mut files = Vec::new();
        images(&engine.home.join("Pictures/Wallpapers"), &mut files, 0);
        files.sort();
        for path in files {
            let mut state = saved.clone();
            state["wallpapers"][key] = json!(path);
            result.push(Choice {
                label: path
                    .file_stem()
                    .unwrap_or_default()
                    .to_string_lossy()
                    .into_owned(),
                image: path,
                state,
                palette: engine.palette(key)?.clone(),
            });
        }
    } else {
        for key in engine.keys() {
            let mut state = saved.clone();
            state["theme"] = json!(key);
            let image = engine.image(&state);
            let thumbnail = image.with_file_name(format!(
                "{}-thumb.png",
                image.file_stem().unwrap_or_default().to_string_lossy()
            ));
            result.push(Choice {
                label: engine.palette(&key)?["name"]
                    .as_str()
                    .unwrap_or(&key)
                    .to_owned(),
                state,
                image: if thumbnail.exists() { thumbnail } else { image },
                palette: engine.palette(&key)?.clone(),
            });
        }
    }
    Ok(result)
}

fn css(p: &Value) -> String {
    let c = |key: &str| p[key].as_str().unwrap_or("#888888");
    format!("window.theme-picker {{ background: {}; color: {}; border: 2px solid {}; border-radius: 18px; }}
      .theme-picker label {{ color: {}; text-shadow: none; }}
      .theme-title {{ font-size: 24px; font-weight: bold; }}
      .theme-subtitle {{ color: {}; font-size: 12px; }}
      .theme-list, .theme-list row {{ background: transparent; }}
      .theme-list row {{ border-radius: 10px; margin: 2px 0; }}
      .theme-list row:selected {{ background: {}; }}
      .theme-list row:selected label {{ color: {}; }}
      .theme-name {{ font-size: 14px; }}
      .theme-sample {{ background: {}; border-radius: 12px; padding: 18px; font-family: 'JetBrainsMono Nerd Font'; }}
      .theme-picker button {{ background-image: none; background: {}; color: {}; border: 1px solid {}; border-radius: 8px; padding: 8px 16px; }}
      .theme-picker button.suggested-action, .theme-picker button.suggested-action label {{ background: {}; color: {}; text-shadow: none; }}",
      c("base"),c("text"),c("accent"),c("text"),c("muted"),c("accent"),c("base"),c("surface"),c("surface"),c("text"),c("overlay"),c("accent"),c("base"))
}

pub fn run(engine: Engine, walls: bool) -> Result<()> {
    let _picker_lock = Lock::new(&engine.state.join("picker.lock"), true)?;
    gtk::init().context("Cannot connect to the desktop")?;
    anyhow::ensure!(
        gtk_layer_shell::is_supported(),
        "This picker needs Wayland layer-shell"
    );
    let saved = engine.saved()?;
    let options = Rc::new(choices(&engine, &saved, walls)?);
    let selected = Rc::new(RefCell::new(saved.clone()));
    let finishing = Rc::new(Cell::new(false));
    let pending = Rc::new(RefCell::new(None::<(Instant, Value)>));
    let error = Rc::new(RefCell::new(None::<String>));
    let (send, receive) = mpsc::channel();
    let (replies, results) = mpsc::channel();
    engine.start_wallpaper();
    let worker_engine = engine.clone();
    let worker = thread::spawn(move || {
        let mut last = saved;
        while let Ok(mut request) = receive.recv() {
            // Keep only the most recent hover. Commit/cancel is always the final request.
            while let Ok(next) = receive.try_recv() {
                request = next;
            }
            match request {
                Request::Preview(state) => {
                    if state != last {
                        match worker_engine.apply(&state, false, true) {
                            Ok(duration) => {
                                let _ =
                                    replies.send(Reply::Applied(duration.as_secs_f64() * 1000.));
                                last = state;
                            }
                            Err(error) => eprintln!("Preview: {error:#}"),
                        }
                    }
                }
                Request::Commit(mut state) => {
                    let key = state["theme"].as_str().unwrap_or("mocha").to_owned();
                    let wall = state["wallpapers"][&key].as_str().map(str::to_owned);
                    let result = (|| -> Result<()> {
                        if let Some(wall) = wall {
                            worker_engine.wallpaper(&mut state, &wall)?;
                        }
                        worker_engine.apply(&state, true, true)?;
                        Ok(())
                    })();
                    if result.is_err() {
                        if let Ok(saved) = worker_engine.saved() {
                            let _ = worker_engine.apply(&saved, false, true);
                        }
                    }
                    let _ = replies.send(Reply::Done(result.err().map(|e| format!("{e:#}"))));
                    return;
                }
                Request::Cancel => {
                    let result = worker_engine
                        .saved()
                        .and_then(|saved| worker_engine.apply(&saved, false, true));
                    let _ = replies.send(Reply::Done(result.err().map(|e| format!("{e:#}"))));
                    return;
                }
            }
        }
        if let Ok(saved) = worker_engine.saved() {
            let _ = worker_engine.apply(&saved, false, true);
        }
    });

    let window = gtk::Window::new(gtk::WindowType::Toplevel);
    window.set_title(if walls {
        "Choose wallpaper"
    } else {
        "Choose theme"
    });
    window.set_widget_name("system-theme-picker");
    window.style_context().add_class("theme-picker");
    window.set_decorated(false);
    window.set_resizable(false);
    window.set_app_paintable(true);
    // Paint an opaque surface ourselves. GTK theme transitions must not expose
    // the terminal behind the picker while the global palette is changing.
    {
        let (palettes, selected) = (engine.palettes.clone(), selected.clone());
        window.connect_draw(move |window, context| {
            let selected = selected.borrow();
            let key = selected["theme"].as_str().unwrap_or("mocha");
            let color = |name: &str| {
                let hex = palettes[key][name].as_str().unwrap_or("#1e1e2e");
                let rgb = u32::from_str_radix(hex.trim_start_matches('#'), 16).unwrap_or(0x1e1e2e);
                (
                    ((rgb >> 16) & 255) as f64 / 255.,
                    ((rgb >> 8) & 255) as f64 / 255.,
                    (rgb & 255) as f64 / 255.,
                )
            };
            let (w, h, r) = (
                window.allocated_width() as f64,
                window.allocated_height() as f64,
                18.,
            );
            let pi = std::f64::consts::PI;
            context.new_sub_path();
            for (x, y, a) in [
                (w - r, r, -pi / 2.),
                (w - r, h - r, 0.),
                (r, h - r, pi / 2.),
                (r, r, pi),
            ] {
                context.arc(x, y, r, a, a + pi / 2.);
            }
            context.close_path();
            let (red, green, blue) = color("base");
            context.set_source_rgb(red, green, blue);
            let _ = context.fill_preserve();
            let (red, green, blue) = color("accent");
            context.set_source_rgb(red, green, blue);
            context.set_line_width(2.);
            let _ = context.stroke();
            glib::Propagation::Proceed
        });
    }
    window.init_layer_shell();
    window.set_namespace("system-theme-picker");
    window.set_layer(Layer::Overlay);
    window.set_keyboard_mode(KeyboardMode::Exclusive);
    window.set_exclusive_zone(0);
    if let (Ok(monitors), Some(display)) =
        (crate::engine::hypr("j/monitors"), gdk::Display::default())
    {
        if let Ok(monitors) = serde_json::from_str::<Value>(&monitors) {
            if let Some(active) = monitors
                .as_array()
                .and_then(|m| m.iter().find(|m| m["focused"] == true))
            {
                for i in 0..display.n_monitors() {
                    if let Some(monitor) = display.monitor(i) {
                        let geometry = monitor.geometry();
                        if active["x"].as_i64() == Some(geometry.x() as i64)
                            && active["y"].as_i64() == Some(geometry.y() as i64)
                        {
                            window.set_monitor(&monitor);
                            break;
                        }
                    }
                }
            }
        }
    }
    let provider = gtk::CssProvider::new();
    let initial_key = selected.borrow()["theme"]
        .as_str()
        .unwrap_or("mocha")
        .to_owned();
    provider.load_from_data(css(engine.palette(&initial_key)?).as_bytes())?;
    gtk::StyleContext::add_provider_for_screen(
        &GtkWindowExt::screen(&window).context("No screen")?,
        &provider,
        gtk::STYLE_PROVIDER_PRIORITY_APPLICATION + 100,
    );
    let root = gtk::Box::new(gtk::Orientation::Vertical, 18);
    root.set_margin_start(24);
    root.set_margin_end(24);
    root.set_margin_top(22);
    root.set_margin_bottom(22);
    let title = gtk::Label::new(Some(if walls {
        "Choose your wallpaper"
    } else {
        "Choose your theme"
    }));
    title.style_context().add_class("theme-title");
    title.set_xalign(0.);
    root.pack_start(&title, false, false, 0);
    let hint = gtk::Label::new(Some(
        "Hover or ↑ ↓ to preview · Enter / click to keep · Esc to restore",
    ));
    hint.style_context().add_class("theme-subtitle");
    hint.set_xalign(0.);
    root.pack_start(&hint, false, false, 0);
    let body = gtk::Box::new(gtk::Orientation::Horizontal, 24);
    let list = gtk::ListBox::new();
    list.style_context().add_class("theme-list");
    list.set_selection_mode(gtk::SelectionMode::Single);
    list.set_activate_on_single_click(true);
    list.set_size_request(300, -1);
    for choice in options.iter() {
        let row = gtk::ListBoxRow::new();
        let hover = gtk::EventBox::new();
        hover.set_above_child(true);
        hover.add_events(gdk::EventMask::ENTER_NOTIFY_MASK | gdk::EventMask::POINTER_MOTION_MASK);
        let content = gtk::Box::new(gtk::Orientation::Horizontal, 10);
        content.set_margin_start(12);
        content.set_margin_end(12);
        content.set_margin_top(14);
        content.set_margin_bottom(14);
        let dot = gtk::Label::new(None);
        dot.set_markup(&format!(
            "<span foreground=\"{}\" size=\"large\">●</span>",
            choice.palette["accent"].as_str().unwrap()
        ));
        content.pack_start(&dot, false, false, 0);
        let label = gtk::Label::new(Some(&choice.label));
        label.set_xalign(0.);
        label.set_ellipsize(gtk::pango::EllipsizeMode::End);
        label.style_context().add_class("theme-name");
        content.pack_start(&label, true, true, 0);
        hover.add(&content);
        row.add(&hover);
        list.add(&row);
        {
            let (list, row) = (list.clone(), row.clone());
            hover.connect_enter_notify_event(move |_, _| {
                list.select_row(Some(&row));
                glib::Propagation::Proceed
            });
        }
        {
            let (list, row) = (list.clone(), row.clone());
            hover.connect_motion_notify_event(move |_, _| {
                list.select_row(Some(&row));
                glib::Propagation::Proceed
            });
        }
    }
    let scroller = gtk::ScrolledWindow::new(None::<&gtk::Adjustment>, None::<&gtk::Adjustment>);
    scroller.set_policy(gtk::PolicyType::Never, gtk::PolicyType::Automatic);
    scroller.set_min_content_height(350);
    scroller.set_max_content_height(420);
    scroller.set_propagate_natural_height(true);
    scroller.add(&list);
    body.pack_start(&scroller, true, true, 0);
    let panel = gtk::Box::new(gtk::Orientation::Vertical, 16);
    panel.set_size_request(350, -1);
    let image = gtk::Image::new();
    panel.pack_start(&image, false, false, 0);
    let sample = gtk::Label::new(None);
    sample.style_context().add_class("theme-sample");
    sample.set_xalign(0.);
    sample.set_yalign(0.);
    panel.pack_start(&sample, false, false, 0);
    let preview_name = gtk::Label::new(None);
    preview_name.set_xalign(0.);
    panel.pack_start(&preview_name, false, false, 0);
    let elapsed = gtk::Label::new(Some("Preview changes are saved only when you select."));
    elapsed.style_context().add_class("theme-subtitle");
    elapsed.set_xalign(0.);
    elapsed.set_line_wrap(true);
    panel.pack_start(&elapsed, false, false, 0);
    body.pack_start(&panel, false, false, 0);
    root.pack_start(&body, true, true, 0);
    let update_view: Rc<dyn Fn(&Choice)> = Rc::new(move |choice| {
        let _ = provider.load_from_data(css(&choice.palette).as_bytes());
        let path = if choice.image.exists() {
            choice.image.clone()
        } else {
            choice.image.with_file_name(
                choice
                    .image
                    .file_name()
                    .unwrap()
                    .to_string_lossy()
                    .replace("-thumb", ""),
            )
        };
        if let Ok(pixbuf) = gtk::gdk_pixbuf::Pixbuf::from_file_at_scale(path, 350, 205, true) {
            image.set_from_pixbuf(Some(&pixbuf));
        }
        let c = |key: &str| choice.palette[key].as_str().unwrap_or("#888888");
        sample.set_markup(&format!("<span foreground=\"{}\">~/projects</span>\n<span foreground=\"{}\">❯</span> <span foreground=\"{}\">nvim</span>\n\n<span foreground=\"{}\">// A little change of scenery</span>\n<span foreground=\"{}\">const</span> theme = <span foreground=\"{}\">\"{}\"</span>;",c("blue"),c("green"),c("text"),c("muted"),c("accent"),c("yellow"),glib::markup_escape_text(&choice.label)));
        preview_name.set_text(&choice.label);
    });
    let initial = options
        .iter()
        .position(|o| o.state == *selected.borrow())
        .unwrap_or(0);
    if let Some(row) = list.row_at_index(initial as i32) {
        list.select_row(Some(&row));
    }
    if let Some(choice) = options.get(initial) {
        update_view(choice);
    }
    {
        let (options, selected, pending, finishing, update_view) = (
            options.clone(),
            selected.clone(),
            pending.clone(),
            finishing.clone(),
            update_view.clone(),
        );
        list.connect_row_selected(move |_, row| {
            if finishing.get() {
                return;
            }
            if let Some(choice) = row.and_then(|r| options.get(r.index() as usize)) {
                *selected.borrow_mut() = choice.state.clone();
                *pending.borrow_mut() = Some((Instant::now(), choice.state.clone()));
                update_view(choice);
            }
        });
    }
    let finish: Rc<dyn Fn(bool)> = {
        let (send, selected, finishing, pending) = (
            send.clone(),
            selected.clone(),
            finishing.clone(),
            pending.clone(),
        );
        Rc::new(move |commit| {
            if finishing.replace(true) {
                return;
            }
            pending.borrow_mut().take();
            let _ = send.send(if commit {
                Request::Commit(selected.borrow().clone())
            } else {
                Request::Cancel
            });
        })
    };
    let footer = gtk::Box::new(gtk::Orientation::Horizontal, 10);
    if walls {
        let open = gtk::Button::with_label("Open image…");
        footer.pack_start(&open, false, false, 0);
        let (window, selected, finish) = (window.clone(), selected.clone(), finish.clone());
        open.connect_clicked(move |_| {
            let dialog = gtk::FileChooserDialog::with_buttons(
                Some("Choose wallpaper"),
                Some(&window),
                gtk::FileChooserAction::Open,
                &[
                    ("Cancel", gtk::ResponseType::Cancel),
                    ("Use image", gtk::ResponseType::Accept),
                ],
            );
            let filter = gtk::FileFilter::new();
            filter.set_name(Some("Images"));
            filter.add_pixbuf_formats();
            dialog.add_filter(filter);
            if dialog.run() == gtk::ResponseType::Accept {
                if let Some(path) = dialog.filename() {
                    let key = selected.borrow()["theme"]
                        .as_str()
                        .unwrap_or("mocha")
                        .to_owned();
                    selected.borrow_mut()["wallpapers"][key] = json!(path);
                    finish(true);
                }
            }
            dialog.close();
        });
    }
    let cancel = gtk::Button::with_label("Cancel");
    let commit = gtk::Button::with_label(if walls { "Use wallpaper" } else { "Use theme" });
    commit.style_context().add_class("suggested-action");
    footer.pack_end(&commit, false, false, 0);
    footer.pack_end(&cancel, false, false, 0);
    {
        let finish = finish.clone();
        cancel.connect_clicked(move |_| finish(false));
    }
    {
        let finish = finish.clone();
        commit.connect_clicked(move |_| finish(true));
    }
    {
        let finish = finish.clone();
        list.connect_row_activated(move |_, _| finish(true));
    }
    {
        let (list, finish) = (list.clone(), finish.clone());
        window.connect_key_press_event(move |_, event| {
            match event.keyval() {
                gdk::keys::constants::Escape => finish(false),
                gdk::keys::constants::Return | gdk::keys::constants::KP_Enter => finish(true),
                gdk::keys::constants::Down
                | gdk::keys::constants::j
                | gdk::keys::constants::Up
                | gdk::keys::constants::k => {
                    let current = list.selected_row().map(|r| r.index()).unwrap_or(0);
                    let delta = if [gdk::keys::constants::Down, gdk::keys::constants::j]
                        .contains(&event.keyval())
                    {
                        1
                    } else {
                        -1
                    };
                    if let Some(row) = list.row_at_index((current + delta).max(0)) {
                        list.select_row(Some(&row));
                        row.grab_focus();
                    }
                }
                _ => return glib::Propagation::Proceed,
            }
            glib::Propagation::Stop
        });
    }
    {
        let finish = finish.clone();
        window.connect_delete_event(move |_, _| {
            finish(false);
            glib::Propagation::Stop
        });
    }
    unsafe {
        libc::signal(libc::SIGTERM, interrupt as *const () as libc::sighandler_t);
        libc::signal(libc::SIGINT, interrupt as *const () as libc::sighandler_t);
    }
    root.pack_end(&footer, false, false, 0);
    window.add(&root);
    window.show_all();
    list.grab_focus();
    {
        let error = error.clone();
        glib::timeout_add_local(Duration::from_millis(16), move || {
            if INTERRUPTED.swap(false, Ordering::Relaxed) {
                finish(false);
            }
            if !finishing.get()
                && pending
                    .borrow()
                    .as_ref()
                    .is_some_and(|(at, _)| at.elapsed() >= Duration::from_millis(75))
            {
                if let Some((_, state)) = pending.borrow_mut().take() {
                    let _ = send.send(Request::Preview(state));
                }
            }
            while let Ok(reply) = results.try_recv() {
                match reply {
                    Reply::Applied(ms) => elapsed.set_text(&format!(
                        "Live preview · {ms:.0} ms\nSelect to keep this look."
                    )),
                    Reply::Done(message) => {
                        *error.borrow_mut() = message;
                        gtk::main_quit();
                        return glib::ControlFlow::Break;
                    }
                }
            }
            glib::ControlFlow::Continue
        });
    }
    gtk::main();
    window.close();
    // The worker finishes rollback/commit before the picker process exits.
    worker
        .join()
        .map_err(|_| anyhow::anyhow!("Theme preview worker stopped unexpectedly"))?;
    if let Some(error) = error.borrow_mut().take() {
        anyhow::bail!(error);
    }
    Ok(())
}
