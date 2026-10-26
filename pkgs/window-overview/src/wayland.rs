use crate::{
    hypr,
    render::{Action, Browse, Capture, CaptureInfo, Renderer, Ui, ViewMode},
};
use anyhow::{bail, Context, Result};
use memmap2::MmapMut;
use std::{
    collections::HashMap,
    fs::File,
    io::{Read, Write},
    os::fd::{AsFd, AsRawFd, OwnedFd},
    os::unix::net::{UnixListener, UnixStream},
    path::PathBuf,
    time::{Duration, Instant},
};
use wayland_client::{
    delegate_noop,
    protocol::{
        wl_buffer, wl_compositor, wl_keyboard, wl_output, wl_pointer, wl_registry, wl_seat, wl_shm,
        wl_shm_pool, wl_surface,
    },
    Connection, Dispatch, QueueHandle, WEnum,
};
use wayland_protocols_hyprland::toplevel_export::v1::client::{
    hyprland_toplevel_export_frame_v1 as export_frame,
    hyprland_toplevel_export_manager_v1 as export_manager,
};
use wayland_protocols_wlr::layer_shell::v1::client::{
    zwlr_layer_shell_v1 as layer_shell, zwlr_layer_surface_v1 as layer_surface,
};
use xkbcommon::xkb;

struct ShmBuffer {
    map: MmapMut,
    buffer: wl_buffer::WlBuffer,
    width: u32,
    height: u32,
    stride: u32,
    busy: bool,
}
impl Drop for ShmBuffer {
    fn drop(&mut self) {
        self.buffer.destroy();
    }
}
struct Pending {
    frame: export_frame::HyprlandToplevelExportFrameV1,
    buffer: Option<ShmBuffer>,
    format: Option<wl_shm::Format>,
    inverted: bool,
    started: Instant,
}
struct Output {
    global: u32,
    name: String,
    proxy: wl_output::WlOutput,
}

struct App {
    compositor: Option<wl_compositor::WlCompositor>,
    shm: Option<wl_shm::WlShm>,
    shell: Option<layer_shell::ZwlrLayerShellV1>,
    exporter: Option<export_manager::HyprlandToplevelExportManagerV1>,
    outputs: Vec<Output>,
    keyboard: Option<wl_keyboard::WlKeyboard>,
    pointer: Option<wl_pointer::WlPointer>,
    xkb: Option<xkb::State>,
    surface: Option<wl_surface::WlSurface>,
    layer: Option<layer_surface::ZwlrLayerSurfaceV1>,
    output_global: Option<u32>,
    width: u32,
    height: u32,
    scale: u32,
    configured: bool,
    dirty: bool,
    buffers: HashMap<u64, ShmBuffer>,
    next_buffer: u64,
    pending: HashMap<String, Pending>,
    captures: HashMap<String, Capture>,
    generation: u64,
    ui: Ui,
    renderer: Renderer,
    last_refresh: Instant,
    number: String,
    number_deadline: Option<Instant>,
    drag: Option<[f32; 2]>,
    pending_focus: Option<(String, String)>,
}
impl App {
    fn new() -> Self {
        Self {
            compositor: None,
            shm: None,
            shell: None,
            exporter: None,
            outputs: Vec::new(),
            keyboard: None,
            pointer: None,
            xkb: None,
            surface: None,
            layer: None,
            output_global: None,
            width: 1920,
            height: 1200,
            scale: 1,
            configured: false,
            dirty: false,
            buffers: HashMap::new(),
            next_buffer: 1,
            pending: HashMap::new(),
            captures: HashMap::new(),
            generation: 0,
            ui: Ui::default(),
            renderer: Renderer::new(),
            last_refresh: Instant::now(),
            number: String::new(),
            number_deadline: None,
            drag: None,
            pending_focus: None,
        }
    }
    fn visible(&self) -> bool {
        self.layer.is_some()
    }
    fn hide(&mut self) {
        if let Some(surface) = &self.surface {
            surface.attach(None, 0, 0);
            surface.commit();
        }
        if let Some(layer) = self.layer.take() {
            layer.destroy();
        }
        if let Some(surface) = self.surface.take() {
            surface.destroy();
        }
        self.configured = false;
        self.dirty = false;
        self.drag = None;
        self.number.clear();
        self.number_deadline = None;
    }
    fn show(&mut self, qh: &QueueHandle<Self>, search: bool) -> Result<()> {
        let snapshot = hypr::snapshot(None)?;
        let target = snapshot
            .monitors
            .iter()
            .find(|m| m.name == snapshot.monitor)
            .context("Monitor disconnected")?;
        let output = self
            .outputs
            .iter()
            .find(|o| o.name == target.name)
            .context("Monitor has no Wayland output")?;
        let proxy = output.proxy.clone();
        let global = output.global;
        let scale = target.scale.ceil().max(1.) as u32;
        let size = target.logical_size();
        self.hide();
        let mode = self.ui.mode;
        let all_sets = self.ui.all_sets;
        self.ui = Ui {
            mode,
            all_sets,
            selected: snapshot
                .clients
                .iter()
                .position(|c| c.address == snapshot.active_address)
                .unwrap_or(0),
            snapshot: Some(snapshot),
            numbers_in_search: search,
            ..Ui::default()
        };
        self.output_global = Some(global);
        self.width = size[0].round() as u32;
        self.height = size[1].round() as u32;
        self.scale = scale;
        let surface = self
            .compositor
            .as_ref()
            .context("Missing wl_compositor")?
            .create_surface(qh, ());
        let layer = self
            .shell
            .as_ref()
            .context("Missing layer shell")?
            .get_layer_surface(
                &surface,
                Some(&proxy),
                layer_shell::Layer::Overlay,
                "window-overview".into(),
                qh,
                (),
            );
        layer.set_anchor(
            layer_surface::Anchor::Top
                | layer_surface::Anchor::Bottom
                | layer_surface::Anchor::Left
                | layer_surface::Anchor::Right,
        );
        layer.set_size(0, 0);
        layer.set_exclusive_zone(-1);
        layer.set_keyboard_interactivity(layer_surface::KeyboardInteractivity::Exclusive);
        surface.set_buffer_scale(scale as i32);
        surface.commit();
        self.surface = Some(surface);
        self.layer = Some(layer);
        self.dirty = true;
        self.refresh(qh)?;
        Ok(())
    }
    fn refresh(&mut self, qh: &QueueHandle<Self>) -> Result<()> {
        let Some(old) = &self.ui.snapshot else {
            return Ok(());
        };
        let selected = old.clients.get(self.ui.selected).map(|c| c.address.clone());
        let snapshot = hypr::snapshot(Some(&old.monitor))?;
        self.ui.selected = selected
            .and_then(|a| snapshot.clients.iter().position(|c| c.address == a))
            .unwrap_or(0);
        self.captures
            .retain(|a, _| snapshot.clients.iter().any(|c| &c.address == a));
        self.ui.snapshot = Some(snapshot);
        self.last_refresh = Instant::now();
        self.dirty = true;
        let exporter = self
            .exporter
            .as_ref()
            .context("Hyprland does not offer window capture")?;
        let expired: Vec<_> = self
            .pending
            .iter()
            .filter(|(_, p)| p.started.elapsed() > Duration::from_secs(3))
            .map(|(a, _)| a.clone())
            .collect();
        for a in expired {
            if let Some(p) = self.pending.remove(&a) {
                p.frame.destroy();
            }
        }
        for client in &self.ui.snapshot.as_ref().unwrap().clients {
            if self.pending.contains_key(&client.address) {
                continue;
            }
            let handle = u64::from_str_radix(client.address.trim_start_matches("0x"), 16)? as u32;
            let frame = exporter.capture_toplevel(0, handle, qh, client.address.clone());
            self.pending.insert(
                client.address.clone(),
                Pending {
                    frame,
                    buffer: None,
                    format: None,
                    inverted: false,
                    started: Instant::now(),
                },
            );
        }
        Ok(())
    }
    fn buffer(
        &mut self,
        w: u32,
        h: u32,
        stride: u32,
        format: wl_shm::Format,
        qh: &QueueHandle<Self>,
    ) -> Result<(u64, ShmBuffer)> {
        let bytes = (stride as usize)
            .checked_mul(h as usize)
            .context("Capture dimensions overflow")?;
        if w == 0 || h == 0 || w > 32768 || h > 32768 || bytes > 512 * 1024 * 1024 {
            bail!("Invalid capture dimensions {w}x{h}");
        }
        let file = tempfile::tempfile()?;
        file.set_len(bytes as u64)?;
        // The mapping remains valid after the pool/file handles are closed. The
        // compositor owns its own reference to the shared-memory descriptor.
        let map = unsafe { MmapMut::map_mut(&file)? };
        let pool = self.shm.as_ref().context("Missing wl_shm")?.create_pool(
            file.as_fd(),
            bytes as i32,
            qh,
            (),
        );
        let id = self.next_buffer;
        self.next_buffer += 1;
        let buffer = pool.create_buffer(0, w as i32, h as i32, stride as i32, format, qh, id);
        pool.destroy();
        Ok((
            id,
            ShmBuffer {
                map,
                buffer,
                width: w,
                height: h,
                stride,
                busy: false,
            },
        ))
    }
    fn render(&mut self, qh: &QueueHandle<Self>) -> Result<()> {
        if !self.visible() || !self.configured || !self.dirty {
            return Ok(());
        }
        let w = self.width * self.scale;
        let h = self.height * self.scale;
        let available = self
            .buffers
            .iter()
            .find(|(_, b)| !b.busy && b.width == w && b.height == h)
            .map(|(&id, _)| id);
        let id = if let Some(id) = available {
            id
        } else {
            if self.buffers.values().filter(|b| b.busy).count() >= 3 {
                return Ok(());
            }
            let (id, buffer) = self.buffer(w, h, w * 4, wl_shm::Format::Xrgb8888, qh)?;
            self.buffers.insert(id, buffer);
            id
        };
        let image = self
            .renderer
            .draw(&mut self.ui, &self.captures, w, h, self.scale);
        let target = self.buffers.get_mut(&id).unwrap();
        // wl_shm XRGB8888 is little-endian B,G,R,X. Captures and the renderer use
        // opaque RGBA, making the conversion independent of application alpha.
        for (dst, src) in target
            .map
            .chunks_exact_mut(4)
            .zip(image.as_raw().chunks_exact(4))
        {
            dst.copy_from_slice(&[src[2], src[1], src[0], 255]);
        }
        let surface = self.surface.as_ref().unwrap();
        surface.attach(Some(&target.buffer), 0, 0);
        surface.damage_buffer(0, 0, w as i32, h as i32);
        surface.commit();
        target.busy = true;
        self.dirty = false;
        self.buffers.retain(|&key, b| key == id || b.busy);
        Ok(())
    }
    fn focus(&mut self, index: usize) -> Result<()> {
        let snapshot = self.ui.snapshot.as_ref().context("No overview open")?;
        if !self.ui.indices().contains(&index) {
            bail!("No matching window selected");
        }
        let client = snapshot.clients.get(index).context("No such window")?;
        self.pending_focus = Some((client.address.clone(), snapshot.monitor.clone()));
        self.hide();
        Ok(())
    }
    fn inspect(&mut self, index: usize) {
        if self
            .ui
            .snapshot
            .as_ref()
            .is_some_and(|s| index < s.clients.len() && self.ui.indices().contains(&index))
        {
            self.ui.selected = index;
            self.ui.inspect = true;
            self.ui.native = true;
            self.ui.pan = [0., 0.];
            self.dirty = true;
        }
    }
    fn act(&mut self, action: Action) -> Result<()> {
        match action {
            Action::Select(i) => self.focus(i)?,
            Action::Inspect(i) => self.inspect(i),
            Action::Workspace(id) => {
                self.ui.workspace = Some(id);
                if self.ui.mode == ViewMode::Windows {
                    self.ui.mode = ViewMode::Workspaces;
                }
            }
            Action::All => {
                self.ui.workspace = None;
                self.ui.query.clear();
            }
            Action::Mode => return self.act(Action::View(self.ui.mode.next())),
            Action::View(mode) => {
                self.ui.inspect = false;
                self.ui.mode = mode;
                self.ui.workspace = None;
            }
            Action::Scope(all) => {
                self.ui.all_sets = all;
                self.ui.workspace = None;
                self.ui.inspect = false;
            }
            Action::Back => self.ui.inspect = false,
            Action::Native => {
                self.ui.native = true;
                self.ui.pan = [0., 0.];
            }
            Action::Fit => {
                self.ui.native = false;
                self.ui.pan = [0., 0.];
            }
            Action::Focus => self.focus(self.ui.selected)?,
        }
        self.number.clear();
        self.number_deadline = None;
        if self.visible() {
            self.dirty = true;
        }
        Ok(())
    }
    fn navigate(&mut self, direction: u32) {
        if self.ui.inspect {
            self.ui.browse(if direction == 105 || direction == 103 {
                Browse::Previous
            } else {
                Browse::Next
            });
        } else {
            let cards: Vec<_> = self.ui.groups.iter().flat_map(|g| &g.cards).collect();
            if let Some(current) = cards.iter().find(|c| c.index == self.ui.selected) {
                let cx = current.rect.x + current.rect.w / 2.;
                let cy = current.rect.y + current.rect.h / 2.;
                let next = cards
                    .iter()
                    .filter_map(|c| {
                        let dx = c.rect.x + c.rect.w / 2. - cx;
                        let dy = c.rect.y + c.rect.h / 2. - cy;
                        let (along, across) = match direction {
                            105 => (-dx, dy.abs()),
                            106 => (dx, dy.abs()),
                            103 => (-dy, dx.abs()),
                            _ => (dy, dx.abs()),
                        };
                        if along > 0.1 {
                            Some((c.index, along + across * 3.))
                        } else {
                            None
                        }
                    })
                    .min_by(|a, b| a.1.total_cmp(&b.1));
                if let Some((index, _)) = next {
                    self.ui.selected = index;
                }
            }
        }
        self.dirty = true;
    }
    fn number(&mut self, ch: char) -> Result<()> {
        if self.ui.snapshot.is_none() {
            return Ok(());
        }
        if self.number.is_empty() && ch == '0' {
            if self.ui.indices().contains(&9) {
                self.focus(9)?;
            }
            return Ok(());
        }
        self.number.push(ch);
        let prefix = &self.number;
        let matches: Vec<_> = self
            .ui
            .indices()
            .into_iter()
            .map(|i| i + 1)
            .filter(|i| i.to_string().starts_with(prefix))
            .collect();
        if matches.is_empty() {
            self.number.clear();
            self.number_deadline = None;
        } else if matches.len() == 1 && matches[0].to_string() == *prefix {
            self.focus(matches[0] - 1)?;
        } else {
            self.number_deadline = Some(Instant::now() + Duration::from_millis(550));
            self.dirty = true;
        }
        Ok(())
    }
    fn back(&mut self) {
        self.number.clear();
        self.number_deadline = None;
        if self.ui.inspect {
            self.ui.inspect = false;
        } else if !self.ui.query.is_empty() {
            self.ui.query.clear();
        } else if self.ui.workspace.is_some() {
            self.ui.workspace = None;
        } else {
            self.hide();
        }
    }
    fn key(&mut self, key: u32, text: String, ctrl: bool, alt: bool) -> Result<()> {
        if !self.visible() {
            return Ok(());
        }
        if ctrl
            || matches!(key, 1 | 14 | 15 | 353 | 102..=109)
            || text.chars().any(|c| !c.is_control() && !c.is_ascii_digit())
        {
            self.number.clear();
            self.number_deadline = None;
        }
        match key {
            1 => self.back(),
            105 if alt => self.back(),
            // With two views, forward and backward both select the other view.
            15 | 353 => self.act(Action::Mode)?,
            102 => self.ui.browse(Browse::First),
            107 => self.ui.browse(Browse::Last),
            104 => self.ui.browse(Browse::Previous),
            109 => self.ui.browse(Browse::Next),
            28 | 96 => {
                if let Ok(n) = self.number.parse::<usize>() {
                    if n > 0 {
                        self.focus(n - 1)?;
                    }
                } else {
                    self.focus(self.ui.selected)?;
                }
            }
            57 if self.ui.inspect => self.ui.inspect = false,
            57 if ctrl || self.ui.query.is_empty() => self.inspect(self.ui.selected),
            2 if ctrl && self.ui.inspect => {
                self.ui.native = true;
                self.ui.pan = [0., 0.];
            }
            11 if ctrl && self.ui.inspect => {
                self.ui.native = false;
                self.ui.pan = [0., 0.];
            }
            105 | 106 | 103 | 108 => self.navigate(key),
            30 if ctrl && !self.ui.inspect => self.act(Action::Scope(!self.ui.all_sets))?,
            33 | 38 if ctrl && !self.ui.inspect => self.ui.numbers_in_search = true,
            22 if ctrl && !self.ui.inspect => self.ui.query.clear(),
            14 if !self.ui.inspect => {
                if ctrl {
                    self.ui.query = self.ui.query.trim_end().to_owned();
                    while self
                        .ui
                        .query
                        .chars()
                        .last()
                        .is_some_and(|c| !c.is_whitespace())
                    {
                        self.ui.query.pop();
                    }
                } else {
                    self.ui.query.pop();
                }
                self.number.clear();
            }
            53 if !self.ui.inspect && self.ui.query.is_empty() => self.ui.numbers_in_search = true,
            _ if !self.ui.inspect => {
                if let Some(ch) = text.chars().next().filter(|c| c.is_ascii_digit()) {
                    if alt || (!self.ui.numbers_in_search && self.ui.query.is_empty()) {
                        self.number(ch)?;
                    } else {
                        self.ui.query.push_str(&text);
                    }
                } else if !ctrl && !alt {
                    self.ui
                        .query
                        .extend(text.chars().filter(|c| !c.is_control()));
                    self.number.clear();
                }
            }
            _ => {}
        }
        if self.visible() {
            self.dirty = true;
        }
        Ok(())
    }
    fn error(&mut self, result: Result<()>) {
        if let Err(error) = result {
            eprintln!("{error:#}");
            self.ui.error = error.to_string();
            self.dirty = true;
        }
    }
    fn command(&mut self, command: &str, qh: &QueueHandle<Self>) -> Result<String> {
        let (cmd, arg) = command
            .trim()
            .split_once(' ')
            .unwrap_or((command.trim(), ""));
        match cmd {
            "toggle" => {
                if self.visible() {
                    self.hide();
                } else {
                    self.show(qh, false)?;
                }
            }
            "open" | "search" => {
                self.show(qh, cmd == "search")?;
            }
            "hide" => self.hide(),
            "cycle" => self.act(Action::Mode)?,
            "view" => self.act(Action::View(match arg {
                "workspaces" => ViewMode::Workspaces,
                "windows" => ViewMode::Windows,
                _ => bail!("Use view workspaces or windows"),
            }))?,
            "scope" => self.act(Action::Scope(match arg {
                "all" => true,
                "current" => false,
                _ => bail!("Use scope current or all"),
            }))?,
            "back" => self.act(Action::All)?,
            "inspect" => self.inspect(arg.parse::<usize>()?.saturating_sub(1)),
            "select" => self.focus(
                arg.parse::<usize>()?
                    .checked_sub(1)
                    .context("Numbers start at 1")?,
            )?,
            "native" => self.act(Action::Native)?,
            "fit" => self.act(Action::Fit)?,
            "workspace" => self.act(Action::Workspace(arg.parse()?))?,
            "query" => {
                self.ui.query = arg.into();
                self.ui.inspect = false;
                self.dirty = true;
            }
            "refresh" => self.refresh(qh)?,
            "dump" => {
                self.renderer
                    .draw(
                        &mut self.ui,
                        &self.captures,
                        self.width * self.scale,
                        self.height * self.scale,
                        self.scale,
                    )
                    .save(arg)?;
            }
            "state" => {
                return Ok(serde_json::to_string(&serde_json::json!({
                    "visible":self.visible(),"monitor":self.ui.snapshot.as_ref().map(|s|&s.monitor),"allMonitors":true,
                    "viewMode":self.ui.mode,"allSets":self.ui.all_sets,"query":self.ui.query,"selected":self.ui.selected+1,
                    "inspection":{"visible":self.ui.inspect,"native":self.ui.native,"pan":self.ui.pan},
                    "size":[self.width,self.height],"scale":self.scale,"groups":self.ui.groups,"setPanels":self.ui.set_panels,
                    "snapshot":self.ui.snapshot,"pendingCaptures":self.pending.len(),"number":self.number,
                    "captures":self.captures.iter().map(|(address,c)|CaptureInfo{address,width:c.width,height:c.height,generation:c.generation}).collect::<Vec<_>>(),
                    "renderMs":self.renderer.last_render_ms,"error":self.ui.error,
                }))? + "\n")
            }
            _ => bail!("Unknown command {cmd}"),
        }
        Ok("ok\n".into())
    }
}

pub fn run(path: PathBuf) -> Result<()> {
    if UnixStream::connect(&path).is_ok() {
        bail!("Overview daemon already running");
    }
    let _ = std::fs::remove_file(&path);
    let listener = UnixListener::bind(&path)?;
    listener.set_nonblocking(true)?;
    let conn = Connection::connect_to_env()?;
    let mut queue = conn.new_event_queue();
    let qh = queue.handle();
    let _registry = conn.display().get_registry(&qh, ());
    let mut app = App::new();
    queue.roundtrip(&mut app)?;
    queue.roundtrip(&mut app)?;
    if app.exporter.is_none() || app.shell.is_none() {
        bail!("Hyprland window export and layer shell are required");
    }
    loop {
        queue.dispatch_pending(&mut app)?;
        while let Ok((mut stream, _)) = listener.accept() {
            stream.set_read_timeout(Some(Duration::from_millis(200)))?;
            let mut bytes = Vec::new();
            Read::by_ref(&mut stream)
                .take(65536)
                .read_to_end(&mut bytes)?;
            let request = String::from_utf8(bytes)?;
            let reply = app
                .command(&request, &qh)
                .unwrap_or_else(|error| format!("error: {error:#}\n"));
            let _ = stream.write_all(reply.as_bytes());
        }
        if let Some((address, monitor)) = app.pending_focus.take() {
            // Wait for layer removal to reach the compositor before focusing.
            conn.flush()?;
            queue.roundtrip(&mut app)?;
            let result = hypr::focus(&address, &monitor);
            app.error(result);
        }
        if app.visible() {
            if app.last_refresh.elapsed() >= Duration::from_secs(1) {
                let result = app.refresh(&qh);
                app.error(result);
            }
            if app.number_deadline.is_some_and(|t| Instant::now() >= t) {
                let number = app.number.parse::<usize>().unwrap_or(0);
                app.number.clear();
                app.number_deadline = None;
                if number > 0 {
                    let result = app.focus(number - 1);
                    app.error(result);
                }
            }
            app.render(&qh)?;
        }
        let wants_write = match conn.flush() {
            Ok(()) => false,
            Err(wayland_client::backend::WaylandError::Io(error))
                if error.kind() == std::io::ErrorKind::WouldBlock =>
            {
                true
            }
            Err(error) => return Err(error.into()),
        };
        if let Some(guard) = conn.prepare_read() {
            let mut fds = [
                libc::pollfd {
                    fd: conn.as_fd().as_raw_fd(),
                    events: libc::POLLIN | if wants_write { libc::POLLOUT } else { 0 },
                    revents: 0,
                },
                libc::pollfd {
                    fd: listener.as_raw_fd(),
                    events: libc::POLLIN,
                    revents: 0,
                },
            ];
            let timeout = if app.visible() { 50 } else { -1 };
            let result =
                unsafe { libc::poll(fds.as_mut_ptr(), fds.len() as libc::nfds_t, timeout) };
            if result < 0 {
                let error = std::io::Error::last_os_error();
                if error.kind() != std::io::ErrorKind::Interrupted {
                    return Err(error.into());
                }
            }
            if fds[0].revents & libc::POLLIN != 0 {
                match guard.read() {
                    Ok(_) => {}
                    Err(wayland_client::backend::WaylandError::Io(error))
                        if matches!(
                            error.kind(),
                            std::io::ErrorKind::WouldBlock | std::io::ErrorKind::Interrupted
                        ) => {}
                    Err(error) => return Err(error.into()),
                }
            }
        }
    }
}

impl Dispatch<wl_registry::WlRegistry, ()> for App {
    fn event(
        state: &mut Self,
        registry: &wl_registry::WlRegistry,
        event: wl_registry::Event,
        _: &(),
        _: &Connection,
        qh: &QueueHandle<Self>,
    ) {
        match event {
            wl_registry::Event::Global {
                name,
                interface,
                version,
            } => match interface.as_str() {
                "wl_compositor" => {
                    state.compositor = Some(registry.bind(name, version.min(4), qh, ()))
                }
                "wl_shm" => state.shm = Some(registry.bind(name, 1, qh, ())),
                "zwlr_layer_shell_v1" => {
                    state.shell = Some(registry.bind(name, version.min(4), qh, ()))
                }
                "hyprland_toplevel_export_manager_v1" => {
                    state.exporter = Some(registry.bind(name, version.min(2), qh, ()))
                }
                "wl_output" => state.outputs.push(Output {
                    global: name,
                    name: String::new(),
                    proxy: registry.bind(name, version.min(4), qh, name),
                }),
                "wl_seat" => {
                    let _: wl_seat::WlSeat = registry.bind(name, version.min(7), qh, ());
                }
                _ => {}
            },
            wl_registry::Event::GlobalRemove { name } => {
                state.outputs.retain(|o| o.global != name);
                if state.output_global == Some(name) {
                    state.hide();
                }
            }
            _ => {}
        }
    }
}
impl Dispatch<wl_output::WlOutput, u32> for App {
    fn event(
        state: &mut Self,
        _: &wl_output::WlOutput,
        event: wl_output::Event,
        data: &u32,
        _: &Connection,
        _: &QueueHandle<Self>,
    ) {
        if let wl_output::Event::Name { name } = event {
            if let Some(output) = state.outputs.iter_mut().find(|o| o.global == *data) {
                output.name = name;
            }
        }
    }
}
impl Dispatch<wl_seat::WlSeat, ()> for App {
    fn event(
        state: &mut Self,
        seat: &wl_seat::WlSeat,
        event: wl_seat::Event,
        _: &(),
        _: &Connection,
        qh: &QueueHandle<Self>,
    ) {
        if let wl_seat::Event::Capabilities {
            capabilities: WEnum::Value(capabilities),
        } = event
        {
            if capabilities.contains(wl_seat::Capability::Keyboard) && state.keyboard.is_none() {
                state.keyboard = Some(seat.get_keyboard(qh, ()));
            }
            if capabilities.contains(wl_seat::Capability::Pointer) && state.pointer.is_none() {
                state.pointer = Some(seat.get_pointer(qh, ()));
            }
        }
    }
}
impl Dispatch<wl_keyboard::WlKeyboard, ()> for App {
    fn event(
        state: &mut Self,
        _: &wl_keyboard::WlKeyboard,
        event: wl_keyboard::Event,
        _: &(),
        _: &Connection,
        _: &QueueHandle<Self>,
    ) {
        match event {
            wl_keyboard::Event::Keymap {
                format: WEnum::Value(wl_keyboard::KeymapFormat::XkbV1),
                fd,
                size,
            } => match load_keymap(fd, size) {
                Ok(keymap) => state.xkb = Some(keymap),
                Err(error) => eprintln!("Keyboard layout: {error:#}"),
            },
            wl_keyboard::Event::Modifiers {
                mods_depressed,
                mods_latched,
                mods_locked,
                group,
                ..
            } => {
                if let Some(xkb) = &mut state.xkb {
                    xkb.update_mask(mods_depressed, mods_latched, mods_locked, 0, 0, group);
                }
            }
            wl_keyboard::Event::Key {
                key,
                state: WEnum::Value(wl_keyboard::KeyState::Pressed),
                ..
            } => {
                let (text, ctrl, alt, shift, symbol) = state
                    .xkb
                    .as_ref()
                    .map(|xkb| {
                        (
                            xkb.key_get_utf8((key + 8).into()),
                            xkb.mod_name_is_active(xkb::MOD_NAME_CTRL, xkb::STATE_MODS_EFFECTIVE),
                            xkb.mod_name_is_active(xkb::MOD_NAME_ALT, xkb::STATE_MODS_EFFECTIVE),
                            xkb.mod_name_is_active(xkb::MOD_NAME_SHIFT, xkb::STATE_MODS_EFFECTIVE),
                            xkb.key_get_one_sym((key + 8).into()).raw(),
                        )
                    })
                    .unwrap_or_default();
                let key = shortcut_key(symbol, ctrl, shift);
                let result = state.key(key, text, ctrl, alt);
                state.error(result);
            }
            _ => {}
        }
    }
}
impl Dispatch<wl_pointer::WlPointer, ()> for App {
    fn event(
        state: &mut Self,
        _: &wl_pointer::WlPointer,
        event: wl_pointer::Event,
        _: &(),
        _: &Connection,
        _: &QueueHandle<Self>,
    ) {
        match event {
            wl_pointer::Event::Enter {
                surface_x,
                surface_y,
                ..
            }
            | wl_pointer::Event::Motion {
                surface_x,
                surface_y,
                ..
            } => {
                let position = [surface_x as f32, surface_y as f32];
                if let Some(old) = state.drag {
                    state.ui.pan[0] += old[0] - position[0];
                    state.ui.pan[1] += old[1] - position[1];
                    state.drag = Some(position);
                    state.dirty = true;
                }
                state.ui.pointer = position;
                if !state.ui.inspect {
                    if let Some((_, Action::Select(index))) = state
                        .ui
                        .hits
                        .iter()
                        .rev()
                        .find(|(r, _)| r.contains(position[0], position[1]))
                    {
                        if state.ui.selected != *index {
                            state.ui.selected = *index;
                            state.dirty = true;
                        }
                    }
                }
            }
            wl_pointer::Event::Button {
                button: 272,
                state: WEnum::Value(button_state),
                ..
            } => {
                if button_state == wl_pointer::ButtonState::Released {
                    state.drag = None;
                    return;
                }
                let p = state.ui.pointer;
                if let Some((_, action)) = state
                    .ui
                    .hits
                    .iter()
                    .rev()
                    .find(|(r, _)| r.contains(p[0], p[1]))
                {
                    let result = state.act(action.clone());
                    state.error(result);
                } else if state.ui.inspect {
                    state.drag = Some(p);
                }
            }
            wl_pointer::Event::Axis {
                axis: WEnum::Value(axis),
                value,
                ..
            } if state.ui.inspect => {
                let index = if axis == wl_pointer::Axis::HorizontalScroll {
                    0
                } else {
                    1
                };
                state.ui.pan[index] += value as f32 * 5.;
                state.dirty = true;
            }
            _ => {}
        }
    }
}
impl Dispatch<layer_surface::ZwlrLayerSurfaceV1, ()> for App {
    fn event(
        state: &mut Self,
        surface: &layer_surface::ZwlrLayerSurfaceV1,
        event: layer_surface::Event,
        _: &(),
        _: &Connection,
        _: &QueueHandle<Self>,
    ) {
        match event {
            layer_surface::Event::Configure {
                serial,
                width,
                height,
            } => {
                surface.ack_configure(serial);
                if width > 0 {
                    state.width = width;
                }
                if height > 0 {
                    state.height = height;
                }
                state.configured = true;
                state.dirty = true;
            }
            layer_surface::Event::Closed => state.hide(),
            _ => {}
        }
    }
}
impl Dispatch<wl_buffer::WlBuffer, u64> for App {
    fn event(
        state: &mut Self,
        _: &wl_buffer::WlBuffer,
        event: wl_buffer::Event,
        id: &u64,
        _: &Connection,
        _: &QueueHandle<Self>,
    ) {
        if let wl_buffer::Event::Release = event {
            if let Some(buffer) = state.buffers.get_mut(id) {
                buffer.busy = false;
            }
        }
    }
}
impl Dispatch<export_frame::HyprlandToplevelExportFrameV1, String> for App {
    fn event(
        state: &mut Self,
        frame: &export_frame::HyprlandToplevelExportFrameV1,
        event: export_frame::Event,
        address: &String,
        _: &Connection,
        qh: &QueueHandle<Self>,
    ) {
        // A timeout/close may have replaced this address's pending request.
        if !state
            .pending
            .get(address)
            .is_some_and(|p| p.frame == *frame)
        {
            return;
        }
        match event {
            export_frame::Event::Buffer {
                format: WEnum::Value(format),
                width,
                height,
                stride,
            } => {
                let result = state.buffer(width, height, stride, format, qh);
                match result {
                    Ok((_, buffer)) => {
                        if let Some(p) = state.pending.get_mut(address) {
                            p.buffer = Some(buffer);
                            p.format = Some(format);
                        }
                    }
                    Err(error) => {
                        eprintln!("capture {address}: {error:#}");
                        frame.destroy();
                        state.pending.remove(address);
                    }
                }
            }
            export_frame::Event::BufferDone => {
                if let Some(buffer) = state.pending.get(address).and_then(|p| p.buffer.as_ref()) {
                    frame.copy(&buffer.buffer, 1);
                } else {
                    frame.destroy();
                    state.pending.remove(address);
                }
            }
            export_frame::Event::Flags {
                flags: WEnum::Value(flags),
            } => {
                if let Some(p) = state.pending.get_mut(address) {
                    p.inverted = flags.contains(export_frame::Flags::YInvert);
                }
            }
            export_frame::Event::Ready { .. } => {
                if let Some(p) = state.pending.remove(address) {
                    if let Some(buffer) = p.buffer {
                        match convert_capture(&buffer, p.format.unwrap(), p.inverted) {
                            Ok(pixels) => {
                                let unchanged = state.captures.get(address).is_some_and(|c| {
                                    c.width == buffer.width
                                        && c.height == buffer.height
                                        && c.pixels == pixels
                                });
                                if !unchanged {
                                    state.generation += 1;
                                    state.captures.insert(
                                        address.clone(),
                                        Capture {
                                            width: buffer.width,
                                            height: buffer.height,
                                            pixels,
                                            generation: state.generation,
                                        },
                                    );
                                    state.dirty = state.visible();
                                }
                            }
                            Err(error) => {
                                eprintln!("capture {address}: {error:#}");
                            }
                        }
                    }
                    frame.destroy();
                }
            }
            export_frame::Event::Failed => {
                state.pending.remove(address);
                frame.destroy();
            }
            _ => {}
        }
    }
}

fn convert_capture(buffer: &ShmBuffer, format: wl_shm::Format, inverted: bool) -> Result<Vec<u8>> {
    let rgb = matches!(format, wl_shm::Format::Xbgr8888 | wl_shm::Format::Abgr8888);
    if !rgb && !matches!(format, wl_shm::Format::Xrgb8888 | wl_shm::Format::Argb8888) {
        bail!("Unsupported capture format {format:?}");
    }
    let mut pixels = vec![255; buffer.width as usize * buffer.height as usize * 4];
    for y in 0..buffer.height as usize {
        let sy = if inverted {
            buffer.height as usize - 1 - y
        } else {
            y
        };
        let source = &buffer.map
            [sy * buffer.stride as usize..sy * buffer.stride as usize + buffer.width as usize * 4];
        let target =
            &mut pixels[y * buffer.width as usize * 4..(y + 1) * buffer.width as usize * 4];
        for (dst, src) in target.chunks_exact_mut(4).zip(source.chunks_exact(4)) {
            if rgb {
                dst[..3].copy_from_slice(&src[..3]);
            } else {
                dst[..3].copy_from_slice(&[src[2], src[1], src[0]]);
            }
        }
    }
    Ok(pixels)
}

delegate_noop!(App: ignore wl_compositor::WlCompositor);
delegate_noop!(App: ignore wl_shm::WlShm);
delegate_noop!(App: ignore wl_shm_pool::WlShmPool);
delegate_noop!(App: ignore wl_surface::WlSurface);
delegate_noop!(App: ignore layer_shell::ZwlrLayerShellV1);
delegate_noop!(App: ignore export_manager::HyprlandToplevelExportManagerV1);

// Resolve shortcuts from layout-aware symbols, including Shift+Tab and Ctrl+A.
fn shortcut_key(symbol: u32, ctrl: bool, shift: bool) -> u32 {
    use xkb::keysyms::*;
    #[allow(non_upper_case_globals)]
    match symbol {
        KEY_Escape => 1,
        KEY_ISO_Left_Tab => 353,
        KEY_Tab if shift => 353,
        KEY_Tab => 15,
        KEY_Return | KEY_KP_Enter => 28,
        KEY_space => 57,
        KEY_BackSpace => 14,
        KEY_Left => 105,
        KEY_Right => 106,
        KEY_Up => 103,
        KEY_Down => 108,
        KEY_Home => 102,
        KEY_End => 107,
        KEY_Page_Up => 104,
        KEY_Page_Down => 109,
        KEY_1 if ctrl => 2,
        KEY_0 if ctrl => 11,
        KEY_a | KEY_A if ctrl => 30,
        KEY_f | KEY_F if ctrl => 33,
        KEY_l | KEY_L if ctrl => 38,
        KEY_u | KEY_U if ctrl => 22,
        KEY_slash => 53,
        _ => 0,
    }
}

fn load_keymap(fd: OwnedFd, size: u32) -> Result<xkb::State> {
    if size == 0 || size > 16 * 1024 * 1024 {
        bail!("Invalid keymap size {size}");
    }
    let file = File::from(fd);
    // wl_keyboard v7 requires MAP_PRIVATE. Reading the descriptor would also
    // depend on its shared file offset, which can be at EOF after a layout swap.
    let map = unsafe {
        memmap2::MmapOptions::new()
            .len(size as usize)
            .map_copy_read_only(&file)?
    };
    let text = std::str::from_utf8(&map)?.trim_end_matches('\0');
    let context = xkb::Context::new(xkb::CONTEXT_NO_FLAGS);
    let keymap = xkb::Keymap::new_from_string(
        &context,
        text.to_owned(),
        xkb::KEYMAP_FORMAT_TEXT_V1,
        xkb::KEYMAP_COMPILE_NO_FLAGS,
    )
    .context("Could not parse compositor keymap")?;
    Ok(xkb::State::new(&keymap))
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn common_shortcuts_resolve_from_keyboard_symbols() {
        use xkb::keysyms::*;
        assert_eq!(shortcut_key(KEY_a, true, false), 30);
        assert_eq!(shortcut_key(KEY_A, true, true), 30);
        assert_eq!(shortcut_key(KEY_a, false, false), 0);
        assert_eq!(shortcut_key(KEY_Tab, false, false), 15);
        assert_eq!(shortcut_key(KEY_Tab, true, false), 15);
        assert_eq!(shortcut_key(KEY_Tab, false, true), 353);
        assert_eq!(shortcut_key(KEY_ISO_Left_Tab, true, true), 353);
        assert_eq!(shortcut_key(KEY_l, true, false), 38);
        assert_eq!(shortcut_key(KEY_Page_Up, false, false), 104);
        assert_eq!(shortcut_key(KEY_Page_Down, false, false), 109);
        assert_eq!(shortcut_key(KEY_Home, false, false), 102);
        assert_eq!(shortcut_key(KEY_End, false, false), 107);
    }
    #[test]
    fn keymap_mapping_ignores_the_shared_descriptor_offset() {
        let text = b"xkb_keymap { xkb_keycodes { minimum=8; maximum=9; <ESC>=9; }; xkb_types { type \"ONE_LEVEL\" { modifiers=None; map[None]=Level1; }; }; xkb_compatibility {}; xkb_symbols { key <ESC> { [ Escape ] }; }; };\0";
        let mut file = tempfile::tempfile().unwrap();
        file.write_all(text).unwrap(); // Deliberately leave the descriptor at EOF.
        let state = load_keymap(file.into(), text.len() as u32).unwrap();
        assert_eq!(
            state.key_get_one_sym(9u32.into()).raw(),
            xkb::keysyms::KEY_Escape
        );
    }
}
