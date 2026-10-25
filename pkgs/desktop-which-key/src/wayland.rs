use crate::{
    model::{self, Binding, Mode, Ui},
    render::Renderer,
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
    process::Command,
    time::{Duration, Instant},
};
use wayland_client::{
    delegate_noop,
    protocol::{
        wl_buffer, wl_compositor, wl_keyboard, wl_output, wl_region, wl_registry, wl_seat, wl_shm,
        wl_shm_pool, wl_surface,
    },
    Connection, Dispatch, QueueHandle, WEnum,
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
    busy: bool,
}
impl Drop for ShmBuffer {
    fn drop(&mut self) {
        self.buffer.destroy();
    }
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
    outputs: Vec<Output>,
    keyboard: Option<wl_keyboard::WlKeyboard>,
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
    ui: Ui,
    renderer: Renderer,
    bindings: Vec<Binding>,
    pending_action: Option<Binding>,
    monitor: String,
}
impl App {
    fn new() -> Result<Self> {
        Ok(Self {
            compositor: None,
            shm: None,
            shell: None,
            outputs: Vec::new(),
            keyboard: None,
            xkb: None,
            surface: None,
            layer: None,
            output_global: None,
            width: 1600,
            height: 780,
            scale: 1,
            configured: false,
            dirty: false,
            buffers: HashMap::new(),
            next_buffer: 1,
            ui: Ui::default(),
            renderer: Renderer::new(),
            bindings: model::load()?,
            pending_action: None,
            monitor: String::new(),
        })
    }
    fn visible(&self) -> bool {
        self.layer.is_some()
    }
    fn hide(&mut self) {
        if let Some(surface) = self.surface.take() {
            surface.attach(None, 0, 0);
            surface.commit();
            if let Some(layer) = self.layer.take() {
                layer.destroy();
            }
            surface.destroy();
        }
        self.configured = false;
        self.dirty = false;
        self.buffers.retain(|_, b| b.busy);
    }
    fn sync(&mut self, qh: &QueueHandle<Self>) -> Result<()> {
        if self.ui.mode == Mode::Hidden {
            self.hide();
            return Ok(());
        }
        let interactive = self.ui.mode == Mode::Pinned;
        if self.visible() {
            self.layer
                .as_ref()
                .unwrap()
                .set_keyboard_interactivity(if interactive {
                    layer_surface::KeyboardInteractivity::Exclusive
                } else {
                    layer_surface::KeyboardInteractivity::None
                });
            self.surface.as_ref().unwrap().commit();
            self.dirty = true;
            return Ok(());
        }
        self.bindings = model::load()?;
        let output = Command::new("hyprctl").args(["-j", "monitors"]).output()?;
        let monitors: Vec<serde_json::Value> = serde_json::from_slice(&output.stdout)?;
        let target = monitors
            .iter()
            .find(|m| m["focused"].as_bool() == Some(true))
            .context("No focused monitor")?;
        self.monitor = target["name"]
            .as_str()
            .context("Missing monitor name")?
            .into();
        let output = self
            .outputs
            .iter()
            .find(|o| o.name == self.monitor)
            .context("Monitor has no Wayland output")?;
        self.output_global = Some(output.global);
        let scale = target["scale"].as_f64().unwrap_or(1.0);
        self.scale = scale.ceil().max(1.) as u32;
        let rotated = target["transform"].as_u64().unwrap_or(0) % 2 == 1;
        let mw = target[if rotated { "height" } else { "width" }]
            .as_f64()
            .unwrap_or(1920.)
            / scale;
        let mh = target[if rotated { "width" } else { "height" }]
            .as_f64()
            .unwrap_or(1080.)
            / scale;
        self.width = ((mw as u32).saturating_sub(64)).clamp(320, 1800);
        let context = matches!(self.ui.mode, Mode::Context(_));
        if context {
            self.width = self.width.min(1120);
        }
        self.height = if context {
            540.min((mh as u32).saturating_sub(64))
        } else {
            ((mh * 0.80) as u32).min(850)
        };
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
                Some(&output.proxy),
                layer_shell::Layer::Overlay,
                "desktop-which-key".into(),
                qh,
                (),
            );
        layer.set_anchor(layer_surface::Anchor::Bottom);
        layer.set_margin(0, 0, 28, 0);
        layer.set_size(self.width, self.height);
        layer.set_exclusive_zone(-1);
        layer.set_keyboard_interactivity(if interactive {
            layer_surface::KeyboardInteractivity::Exclusive
        } else {
            layer_surface::KeyboardInteractivity::None
        });
        let region = self.compositor.as_ref().unwrap().create_region(qh, ());
        surface.set_input_region(Some(&region));
        region.destroy();
        surface.set_buffer_scale(self.scale as i32);
        surface.commit();
        self.surface = Some(surface);
        self.layer = Some(layer);
        self.dirty = true;
        Ok(())
    }
    fn buffer(&mut self, w: u32, h: u32, qh: &QueueHandle<Self>) -> Result<(u64, ShmBuffer)> {
        let bytes = (w as usize)
            .checked_mul(h as usize)
            .and_then(|n| n.checked_mul(4))
            .context("Buffer overflow")?;
        if bytes > 128 * 1024 * 1024 {
            bail!("Overlay buffer too large");
        }
        let file = tempfile::tempfile()?;
        file.set_len(bytes as u64)?;
        let map = unsafe { MmapMut::map_mut(&file)? };
        let pool = self.shm.as_ref().context("Missing wl_shm")?.create_pool(
            file.as_fd(),
            bytes as i32,
            qh,
            (),
        );
        let id = self.next_buffer;
        self.next_buffer += 1;
        let buffer = pool.create_buffer(
            0,
            w as i32,
            h as i32,
            (w * 4) as i32,
            wl_shm::Format::Xrgb8888,
            qh,
            id,
        );
        pool.destroy();
        Ok((
            id,
            ShmBuffer {
                map,
                buffer,
                width: w,
                height: h,
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
        self.buffers
            .retain(|_, b| b.busy || (b.width == w && b.height == h));
        let id = if let Some((&id, _)) = self
            .buffers
            .iter()
            .find(|(_, b)| !b.busy && b.width == w && b.height == h)
        {
            id
        } else {
            if self.buffers.values().filter(|b| b.busy).count() >= 3 {
                return Ok(());
            }
            let (id, buffer) = self.buffer(w, h, qh)?;
            self.buffers.insert(id, buffer);
            id
        };
        let image = self.renderer.draw(
            &mut self.ui,
            &self.bindings,
            self.width,
            self.height,
            self.scale,
        );
        let buffer = self.buffers.get_mut(&id).unwrap();
        for (dst, src) in buffer
            .map
            .chunks_exact_mut(4)
            .zip(image.as_raw().chunks_exact(4))
        {
            dst.copy_from_slice(&[src[2], src[1], src[0], 255]);
        }
        buffer.busy = true;
        let surface = self.surface.as_ref().unwrap();
        surface.attach(Some(&buffer.buffer), 0, 0);
        surface.damage_buffer(0, 0, w as i32, h as i32);
        surface.commit();
        self.dirty = false;
        Ok(())
    }
    fn key(
        &mut self,
        symbol: u32,
        text: String,
        ctrl: bool,
        alt: bool,
        logo: bool,
        qh: &QueueHandle<Self>,
    ) -> Result<()> {
        if self.ui.mode != Mode::Pinned {
            return Ok(());
        }
        use xkb::keysyms::*;
        let len = self.ui.filtered(&self.bindings).len();
        #[allow(non_upper_case_globals)]
        match symbol {
            KEY_F9 => self.ui.open(Mode::Hidden),
            KEY_Escape if logo => self.ui.open(Mode::Hidden),
            KEY_m | KEY_M if logo => self.ui.open(Mode::Hidden),
            KEY_Escape => self.ui.escape(),
            KEY_F1 => self.ui.help = !self.ui.help,
            KEY_question if !self.ui.search => self.ui.help = !self.ui.help,
            KEY_slash if !self.ui.search => {
                self.ui.search = true;
                self.ui.help = false;
            }
            KEY_f | KEY_F if ctrl => {
                self.ui.search = true;
                self.ui.help = false;
            }
            KEY_u | KEY_U if ctrl => {
                self.ui.query.clear();
                self.ui.selected = 0;
            }
            KEY_Tab | KEY_ISO_Left_Tab => self.ui.search = !self.ui.search,
            KEY_Up => self.ui.move_by(-1, len),
            KEY_Down => self.ui.move_by(1, len),
            KEY_Page_Up => self.ui.move_by(-(self.ui.page_size as isize), len),
            KEY_Page_Down => self.ui.move_by(self.ui.page_size as isize, len),
            KEY_Home if !self.ui.search => self.ui.selected = 0,
            KEY_End if !self.ui.search => self.ui.selected = len.saturating_sub(1),
            KEY_BackSpace if self.ui.search => {
                self.ui.query.pop();
                self.ui.selected = 0;
            }
            KEY_Return | KEY_KP_Enter if !self.ui.help => {
                if let Some(binding) = self
                    .ui
                    .filtered(&self.bindings)
                    .get(self.ui.selected)
                    .cloned()
                    .cloned()
                {
                    if binding.executable() {
                        self.pending_action = Some(binding);
                        self.ui.open(Mode::Hidden);
                    } else {
                        self.ui.error = "Use the displayed gesture after closing the map".into();
                    }
                }
            }
            _ if self.ui.search && !ctrl && !alt && !self.ui.help => {
                self.ui
                    .query
                    .extend(text.chars().filter(|c| !c.is_control()));
                self.ui.selected = 0;
            }
            _ => {}
        }
        self.sync(qh)
    }
    fn command(&mut self, command: &str, qh: &QueueHandle<Self>) -> Result<String> {
        let (cmd, arg) = command
            .trim()
            .split_once(' ')
            .unwrap_or((command.trim(), ""));
        match cmd {
            "hold-start" => self.ui.hold_start(),
            "hold-end" => self.ui.hold_end(),
            "toggle" => {
                self.hide();
                if self.ui.mode == Mode::Pinned {
                    self.ui.open(Mode::Hidden);
                } else {
                    self.ui.open(Mode::Pinned);
                }
            }
            "show" => {
                self.hide();
                self.ui.open(Mode::Pinned);
            }
            "hide" => self.ui.open(Mode::Hidden),
            "context" => {
                self.hide();
                self.ui.open(Mode::Context(arg.into()));
            }
            "end-context" => {
                if matches!(self.ui.mode, Mode::Context(_)) {
                    self.ui.open(Mode::Hidden);
                }
            }
            "search" => {
                self.hide();
                self.ui.open(Mode::Pinned);
                self.ui.search = true;
                self.ui.query = arg.into();
            }
            "refresh" => {
                self.bindings = model::load()?;
            }
            "dump" => {
                self.renderer
                    .draw(
                        &mut self.ui,
                        &self.bindings,
                        self.width,
                        self.height,
                        self.scale,
                    )
                    .save(arg)?;
            }
            "state" => {
                return Ok(serde_json::to_string(
                    &serde_json::json!({"mode":self.ui.mode,"visible":self.visible(),"interactive":self.ui.mode==Mode::Pinned,"monitor":self.monitor,"size":[self.width,self.height],"scale":self.scale,"search":self.ui.search,"help":self.ui.help,"query":self.ui.query,"selected":self.ui.selected,"pageSize":self.ui.page_size,"total":self.bindings.len(),"matches":self.ui.filtered(&self.bindings),"pendingHold":self.ui.deadline.is_some(),"error":self.ui.error}),
                )? + "\n")
            }
            _ => bail!("Unknown command {cmd}"),
        }
        self.sync(qh)?;
        Ok("ok\n".into())
    }
}
pub fn run(path: PathBuf) -> Result<()> {
    if UnixStream::connect(&path).is_ok() {
        bail!("Which-key daemon already running");
    }
    let _ = std::fs::remove_file(&path);
    let listener = UnixListener::bind(&path)?;
    listener.set_nonblocking(true)?;
    let conn = Connection::connect_to_env()?;
    let mut queue = conn.new_event_queue();
    let qh = queue.handle();
    let _registry = conn.display().get_registry(&qh, ());
    let mut app = App::new()?;
    queue.roundtrip(&mut app)?;
    queue.roundtrip(&mut app)?;
    if app.shell.is_none() {
        bail!("Wayland layer shell is required");
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
        if let Some(action) = app.pending_action.take() {
            conn.flush()?;
            queue.roundtrip(&mut app)?;
            // Reset any existing sequence before dispatching the original action.
            Command::new("hyprctl")
                .args(["dispatch", "submap", "reset"])
                .output()?;
            let result = Command::new("hyprctl")
                .args(["dispatch", &action.dispatcher, &action.arg])
                .output()?;
            if !result.status.success() {
                eprintln!("Action failed: {}", String::from_utf8_lossy(&result.stdout));
            }
        }
        if app.ui.deadline.is_some_and(|t| Instant::now() >= t) {
            app.ui.deadline = None;
            if app.ui.mode == Mode::Hidden {
                app.ui.open(Mode::Peek);
                if let Err(e) = app.sync(&qh) {
                    eprintln!("Peek: {e:#}");
                    app.ui.open(Mode::Hidden);
                }
            }
        }
        app.render(&qh)?;
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
            let timeout = if app.ui.deadline.is_some() { 10 } else { -1 };
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
                    state.ui.open(Mode::Hidden);
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
        qh: &QueueHandle<Self>,
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
                let (text, ctrl, alt, logo, symbol) = state
                    .xkb
                    .as_ref()
                    .map(|xkb| {
                        (
                            xkb.key_get_utf8((key + 8).into()),
                            xkb.mod_name_is_active(xkb::MOD_NAME_CTRL, xkb::STATE_MODS_EFFECTIVE),
                            xkb.mod_name_is_active(xkb::MOD_NAME_ALT, xkb::STATE_MODS_EFFECTIVE),
                            xkb.mod_name_is_active(xkb::MOD_NAME_LOGO, xkb::STATE_MODS_EFFECTIVE),
                            xkb.key_get_one_sym((key + 8).into()).raw(),
                        )
                    })
                    .unwrap_or_default();
                if let Err(e) = state.key(symbol, text, ctrl, alt, logo, qh) {
                    eprintln!("Input: {e:#}");
                }
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
            layer_surface::Event::Closed => {
                state.ui.open(Mode::Hidden);
                state.hide();
            }
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
delegate_noop!(App: ignore wl_compositor::WlCompositor);
delegate_noop!(App: ignore wl_shm::WlShm);
delegate_noop!(App: ignore wl_shm_pool::WlShmPool);
delegate_noop!(App: ignore wl_surface::WlSurface);
delegate_noop!(App: ignore wl_region::WlRegion);
delegate_noop!(App: ignore layer_shell::ZwlrLayerShellV1);

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
