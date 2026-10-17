//! Short-lived clipboard offers with notification when Firefox reads the file
//! URI. Waiting for the actual read avoids racing a busy browser or replacing
//! its clipboard with the next file before the previous paste has started.
use crate::transfer;
use anyhow::{bail, Context, Result};
use std::{
    env,
    fs::File,
    io::{self, BufRead, Read, Write},
    os::unix::{
        ffi::{OsStrExt, OsStringExt},
        process::CommandExt,
    },
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
    sync::mpsc::{self, Receiver, RecvTimeoutError},
    time::Duration,
};
use url::Url;
use wayland_client::{
    delegate_noop,
    protocol::{wl_registry, wl_seat},
    Connection, Dispatch, QueueHandle,
};
use wayland_protocols_wlr::data_control::v1::client::{
    zwlr_data_control_device_v1::{self, ZwlrDataControlDeviceV1},
    zwlr_data_control_manager_v1::ZwlrDataControlManagerV1,
    zwlr_data_control_offer_v1::ZwlrDataControlOfferV1,
    zwlr_data_control_source_v1::{self, ZwlrDataControlSourceV1},
};

pub struct Offer {
    child: Child,
    events: Receiver<String>,
}

impl Drop for Offer {
    fn drop(&mut self) {
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}

impl Offer {
    pub fn publish(file: &Path) -> Result<Self> {
        let mut child = Command::new(env::current_exe()?)
            .arg("--serve-attachment")
            .process_group(0)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::null())
            .spawn()?;
        let stdout = child.stdout.take().unwrap();
        let (tx, events) = mpsc::channel();
        std::thread::spawn(move || {
            for line in io::BufReader::new(stdout).lines().map_while(Result::ok) {
                if tx.send(line).is_err() {
                    break;
                }
            }
        });
        let mut offer = Self { child, events };
        offer
            .child
            .stdin
            .take()
            .unwrap()
            .write_all(file.as_os_str().as_bytes())?;
        if offer.events.recv_timeout(Duration::from_secs(8))? != "READY" {
            bail!("Could not publish the file attachment clipboard");
        }
        Ok(offer)
    }

    pub fn was_read(&self, timeout: Duration) -> Result<bool> {
        match self.events.recv_timeout(timeout) {
            Ok(event) if event == "READ" => Ok(true),
            Ok(_) => bail!("The attachment clipboard was replaced"),
            Err(RecvTimeoutError::Timeout) => Ok(false),
            Err(RecvTimeoutError::Disconnected) => bail!("The attachment clipboard owner exited"),
        }
    }
}

#[derive(Default)]
struct State {
    manager: Option<ZwlrDataControlManagerV1>,
    seat: Option<wl_seat::WlSeat>,
    uri: Vec<u8>,
    path: Vec<u8>,
    done: bool,
    ready: bool,
    error: Option<io::Error>,
}

impl Dispatch<wl_registry::WlRegistry, ()> for State {
    fn event(
        state: &mut Self,
        registry: &wl_registry::WlRegistry,
        event: wl_registry::Event,
        _: &(),
        _: &Connection,
        qh: &QueueHandle<Self>,
    ) {
        if let wl_registry::Event::Global {
            name,
            interface,
            version,
        } = event
        {
            match interface.as_str() {
                "zwlr_data_control_manager_v1" => {
                    state.manager = Some(registry.bind(name, version.min(2), qh, ()))
                }
                "wl_seat" if state.seat.is_none() => {
                    state.seat = Some(registry.bind(name, version.min(5), qh, ()))
                }
                _ => {}
            }
        }
    }
}

impl Dispatch<ZwlrDataControlSourceV1, ()> for State {
    fn event(
        state: &mut Self,
        _: &ZwlrDataControlSourceV1,
        event: zwlr_data_control_source_v1::Event,
        _: &(),
        _: &Connection,
        _: &QueueHandle<Self>,
    ) {
        match event {
            zwlr_data_control_source_v1::Event::Send { mime_type, fd } => {
                let bytes = match mime_type.as_str() {
                    "text/uri-list" => state.uri.as_slice(),
                    "text/plain" | "text/plain;charset=utf-8" => state.path.as_slice(),
                    "x-kde-passwordManagerHint" => b"secret",
                    _ => return,
                };
                // The offered bytes are tiny file references, never contents.
                // Drop the fd before acknowledging so Firefox observes EOF.
                let result = File::from(fd).write_all(bytes);
                if let Err(error) = result {
                    if error.kind() != io::ErrorKind::BrokenPipe {
                        state.error = Some(error);
                        state.done = true;
                    }
                } else if mime_type == "text/uri-list" && state.ready {
                    if let Err(error) = signal("READ") {
                        state.error = Some(error);
                        state.done = true;
                    }
                }
            }
            zwlr_data_control_source_v1::Event::Cancelled => state.done = true,
            _ => {}
        }
    }
}

impl Dispatch<ZwlrDataControlDeviceV1, ()> for State {
    fn event(
        state: &mut Self,
        _: &ZwlrDataControlDeviceV1,
        event: zwlr_data_control_device_v1::Event,
        _: &(),
        _: &Connection,
        _: &QueueHandle<Self>,
    ) {
        match event {
            zwlr_data_control_device_v1::Event::DataOffer { id } => id.destroy(),
            zwlr_data_control_device_v1::Event::Finished => state.done = true,
            _ => {}
        }
    }

    wayland_client::event_created_child!(State, ZwlrDataControlDeviceV1, [
        0 => (ZwlrDataControlOfferV1, ())
    ]);
}

delegate_noop!(State: ignore wl_seat::WlSeat);
delegate_noop!(State: ignore ZwlrDataControlManagerV1);
delegate_noop!(State: ignore ZwlrDataControlOfferV1);

fn signal(message: &str) -> io::Result<()> {
    let mut output = io::stdout().lock();
    writeln!(output, "{message}")?;
    output.flush()
}

pub fn serve_attachment() -> Result<()> {
    let mut path = Vec::new();
    io::stdin().read_to_end(&mut path)?;
    let files = transfer::validate(&[PathBuf::from(std::ffi::OsString::from_vec(path))])?;
    let path = &files[0];
    let uri = Url::from_file_path(path).map_err(|_| anyhow::anyhow!("Invalid file URI"))?;
    let connection = Connection::connect_to_env()?;
    let mut queue = connection.new_event_queue();
    let qh = queue.handle();
    let _registry = connection.display().get_registry(&qh, ());
    let mut state = State {
        uri: format!("{uri}\r\n").into_bytes(),
        path: path.as_os_str().as_bytes().to_vec(),
        ..State::default()
    };
    queue.roundtrip(&mut state)?;
    let manager = state
        .manager
        .as_ref()
        .context("Wayland data control is unavailable")?;
    let seat = state.seat.as_ref().context("No Wayland seat")?;
    let device = manager.get_data_device(seat, &qh, ());
    let source = manager.create_data_source(&qh, ());
    for mime in [
        "text/uri-list",
        "text/plain;charset=utf-8",
        "text/plain",
        "x-kde-passwordManagerHint",
    ] {
        source.offer(mime.to_owned());
    }
    device.set_selection(Some(&source));
    // Confirm the compositor has installed this offer before the paste key is
    // issued. Ignore any initial clipboard-manager reads during registration.
    queue.roundtrip(&mut state)?;
    state.ready = true;
    signal("READY")?;
    while !state.done {
        queue.blocking_dispatch(&mut state)?;
    }
    if let Some(error) = state.error {
        return Err(error.into());
    }
    Ok(())
}
