mod attach;
mod cache;
mod clipboard;
mod search;
mod transfer;
mod ui;

use anyhow::{bail, Context, Result};
use clap::Parser;
use std::{
    io::{self, IsTerminal, Write},
    path::PathBuf,
};

#[derive(Parser, Debug)]
#[command(
    version,
    about = "Find files, select with Vim keys, then copy or drag them.",
    after_help = "Type to search; Esc for Vim mode; j/k move; Space/Tab select; v selects a range;\nEnter attaches to Firefox from the desktop launcher, otherwise copies; y copies files;\nd opens a drag window; Y copies paths; q quits.\nDefault: cached documents, downloads, media, projects, and dotfiles. --all widens scope."
)]
struct Args {
    /// Search a specific folder instead of the personal file index
    #[arg(conflicts_with = "system")]
    root: Option<PathBuf>,
    /// Search /, excluding virtual filesystems and the Nix store
    #[arg(long)]
    system: bool,
    /// Search all files, including hidden, ignored, and generated files
    #[arg(short, long)]
    all: bool,
    /// Rebuild the index even if folder timestamps are unchanged
    #[arg(long)]
    refresh: bool,
    /// Update the persistent index without opening the picker
    #[arg(long, conflicts_with_all = ["copy", "drag_last", "print", "print0"])]
    index: bool,
    /// Start with this fuzzy search
    #[arg(short, long, default_value = "")]
    query: String,
    /// Print selected paths instead of copying (also works over SSH)
    #[arg(long, conflicts_with_all = ["print0", "copy", "drag_last"])]
    print: bool,
    /// Print NUL-separated selected paths instead of copying
    #[arg(long, conflicts_with_all = ["copy", "drag_last"])]
    print0: bool,
    /// Copy these files directly, without opening the picker
    #[arg(long, num_args = 1.., conflicts_with_all = ["root", "system", "drag_last"])]
    copy: Vec<PathBuf>,
    /// Open a drag window for the last copied selection
    #[arg(long, conflicts_with_all = ["root", "system", "copy"])]
    drag_last: bool,
    #[arg(long, hide = true)]
    serve_clipboard: bool,
    #[arg(long, hide = true)]
    serve_attachment: bool,
    #[arg(long, hide = true)]
    paths: bool,
    /// Destination captured by the desktop launcher before it takes focus
    #[arg(long, hide = true)]
    destination: Option<String>,
}

fn run() -> Result<()> {
    let args = Args::parse();
    if args.serve_attachment {
        return clipboard::serve_attachment();
    }
    if args.serve_clipboard {
        return transfer::serve(args.paths);
    }
    if args.drag_last {
        return transfer::drag(&transfer::load_selection()?);
    }
    if !args.copy.is_empty() {
        let files = transfer::validate(&args.copy)?;
        transfer::copy(&files, false)?;
        transfer::save_selection(&files)?;
        eprintln!(
            "Copied {} file(s). Paste with Ctrl+V, or run filepick --drag-last.",
            files.len()
        );
        return Ok(());
    }
    let personal = args.root.is_none() && !args.system;
    let root = if args.system {
        PathBuf::from("/")
    } else {
        args.root.unwrap_or(transfer::home()?)
    }
    .canonicalize()
    .context("Cannot access search folder")?;
    if !root.is_dir() {
        bail!("Search root must be a folder: {}", root.display());
    }
    if args.index {
        let start = std::time::Instant::now();
        let stats = search::index(root, args.all, personal, args.refresh)?;
        println!(
            "{} files · {} folder/ignore stamps · {} · {:.0} ms",
            stats.files,
            stats.directories,
            if stats.cached {
                "cache up to date"
            } else {
                "index rebuilt"
            },
            start.elapsed().as_secs_f64() * 1000.0
        );
        return Ok(());
    }
    if !io::stdin().is_terminal() || !io::stderr().is_terminal() {
        bail!("The picker needs a terminal. Use --copy FILE... or --index without a terminal.");
    }
    let Some((files, action)) = ui::pick(root, args.all, args.query, personal, args.refresh)?
    else {
        return Ok(());
    };
    let files = transfer::validate(&files)?;
    if args.print || args.print0 {
        let mut stdout = io::stdout().lock();
        for file in files {
            use std::os::unix::ffi::OsStrExt;
            stdout.write_all(file.as_os_str().as_bytes())?;
            stdout.write_all(if args.print0 { b"\0" } else { b"\n" })?;
        }
    } else {
        // Preserve a working drag fallback even if the clipboard is unavailable.
        if action == ui::Action::Drag {
            transfer::save_selection(&files)?;
            if let Err(err) = transfer::copy(&files, false) {
                eprintln!("Clipboard unavailable ({err:#}); opening drag window.");
            }
            return transfer::drag(&files);
        }
        transfer::copy(&files, action == ui::Action::Paths)?;
        transfer::save_selection(&files)?;
        if action == ui::Action::Attach {
            if let Some(destination) = args
                .destination
                .as_deref()
                .map(attach::Destination::parse)
                .transpose()?
                .flatten()
            {
                let result = attach::paste(&files, &destination);
                match &result {
                    Ok(()) => transfer::notify(&format!("Sent {} files to Firefox.", files.len())),
                    Err(error) => transfer::notify(&format!("{error:#}")),
                }
                return result;
            }
        }
        if args.destination.is_some() {
            transfer::notify_copied(files.len(), action == ui::Action::Paths);
        }
        eprintln!(
            "Copied {} {}. Paste with Ctrl+V; filepick --drag-last opens a drag window.",
            files.len(),
            if action == ui::Action::Paths {
                "path(s)"
            } else {
                "file(s)"
            }
        );
    }
    Ok(())
}

fn main() {
    if let Err(error) = run() {
        eprintln!("filepick: {error:#}");
        std::process::exit(1);
    }
}
