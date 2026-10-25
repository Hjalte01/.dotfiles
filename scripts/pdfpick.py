#!/usr/bin/env python3
"""Fuzzy PDF library picker with download and Zathura history views."""

import argparse
from collections import Counter
from contextlib import closing
from datetime import datetime
import json
import os
from pathlib import Path
import shlex
import sqlite3
import subprocess
import sys
import tempfile
import time


EXCLUDES = (
    "node_modules", "target", "vendor", "venv", "env", "__pycache__",
    "build", "dist", "Cache", "Caches", "cache", "caches", "steamapps",
)
PARTIAL_SUFFIXES = (".part", ".crdownload", ".download", ".tmp", ".filepart", ".aria2")
VIEWS = {"all": "All PDFs · newest added", "downloads": "Downloads · newest added",
         "opened": "Opened · most recent"}


def xdg(name, fallback):
    return Path(os.environ.get(name) or Path.home() / fallback)


def clean(text):
    """Keep filenames and extracted PDF text from injecting terminal controls."""
    return "".join(c if c.isprintable() or c == "\n" else " " for c in str(text))


def label(path):
    try:
        return "~/" + str(path.relative_to(Path.home()))
    except ValueError:
        return str(path)


def downloads_directory():
    try:
        result = subprocess.run(["xdg-user-dir", "DOWNLOAD"], check=True,
                                capture_output=True, text=True, timeout=3)
        if result.stdout.strip():
            return Path(result.stdout.strip()).absolute()
    except (OSError, subprocess.SubprocessError):
        pass
    return Path.home() / "Downloads"


def search_roots(explicit):
    if explicit:
        return [Path(p).expanduser().absolute() for p in explicit]
    config = xdg("XDG_CONFIG_HOME", ".config") / "pdfpick/roots"
    lines = config.read_text().splitlines() if config.is_file() else ["."]
    return [Path.home() / line.strip().removeprefix("~/") for line in lines
            if line.strip() and not line.lstrip().startswith("#")]


def history():
    recent = {}
    sources = (
        (xdg("XDG_DATA_HOME", ".local/share") / "zathura/bookmarks.sqlite",
         "SELECT file, CAST(strftime('%s', time) AS REAL) FROM fileinfo"),
        (xdg("XDG_STATE_HOME", ".local/state") / "pdfpick/history.sqlite",
         "SELECT file, opened FROM opened"),
    )
    for database, query in sources:
        if not database.is_file():
            continue
        try:
            with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True,
                                         timeout=0.2)) as connection:
                for filename, stamp in connection.execute(query):
                    if stamp is not None:
                        path = str(Path(filename).absolute())
                        recent[path] = max(recent.get(path, 0), float(stamp))
        except sqlite3.Error as error:
            print(f"pdfpick: cannot read {database.name}: {error}", file=sys.stderr)
    return recent


def record_opened(paths):
    directory = xdg("XDG_STATE_HOME", ".local/state") / "pdfpick"
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    database = directory / "history.sqlite"
    descriptor = os.open(database, os.O_CREAT | os.O_WRONLY, 0o600)
    os.close(descriptor)
    with closing(sqlite3.connect(database)) as connection, connection:
        connection.execute("CREATE TABLE IF NOT EXISTS opened "
                           "(file TEXT PRIMARY KEY, opened REAL NOT NULL)")
        connection.executemany("INSERT OR REPLACE INTO opened VALUES (?, ?)",
                               [(str(p), time.time()) for p in paths])


def scan(roots, include_hidden=False, include_history=True):
    roots = [p for p in roots if p.is_dir()]
    if not roots:
        return []
    command = ["fd", "--type", "f", "--extension", "pdf", "--ignore-case",
               "--no-ignore", "--absolute-path", "--print0", "--color", "never"]
    if include_hidden:
        command.append("--hidden")
    else:
        for name in EXCLUDES:
            command.extend(["--exclude", name])
    result = subprocess.run([*command, ".", *map(str, roots)], check=True,
                            capture_output=True)
    # Include existing Zathura history outside the search roots, too.
    paths = {os.fsdecode(p) for p in result.stdout.split(b"\0") if p}
    if include_history:
        paths.update(p for p in history() if Path(p).suffix.lower() == ".pdf")
    entries = []
    for filename in sorted(paths):
        path = Path(filename)
        try:
            info = path.stat()
            if not path.is_file() or not info.st_size:
                continue
            if any(path.with_name(path.name + suffix).exists() for suffix in PARTIAL_SUFFIXES):
                continue
            entries.append({"path": filename, "added": max(info.st_ctime, info.st_mtime)})
        except OSError:
            continue
    return entries


def view_entries(entries, view, folder, downloads, recent):
    filtered = [entry for entry in entries
                if (folder is None or Path(entry["path"]).is_relative_to(folder))
                and (view != "downloads" or Path(entry["path"]).is_relative_to(downloads))
                and (view != "opened" or entry["path"] in recent)]
    return sorted(filtered, key=lambda entry: (
        -(recent.get(entry["path"], 0) if view == "opened" else entry["added"]),
        entry["path"].casefold()))


def date(stamp):
    return datetime.fromtimestamp(stamp).strftime("%Y-%m-%d %H:%M")


def preview(index_file, index):
    entries = json.loads(Path(index_file).read_text())
    entry = entries[int(index)]
    path = Path(entry["path"])
    print(clean(label(path)), flush=True)
    print(f"\nAdded/changed: {date(entry['added'])}\n", flush=True)
    try:
        result = subprocess.run(["pdftotext", "-f", "1", "-l", "2", "-layout",
                                 str(path), "-"], capture_output=True, timeout=4)
        content = result.stdout.decode("utf-8", errors="replace").strip()
        print(clean(content[:24000]) if content else "No text preview (scanned or encrypted PDF).")
    except subprocess.TimeoutExpired:
        print("Text preview timed out. Enter opens the PDF in Zathura.")


def choose(rows, prompt, header, query="", preview_command=None, multiple=False,
           switches=True):
    command = ["fzf", "--read0", "--print0", "--print-query", "--layout=reverse",
               "--border=rounded", "--delimiter=\t", "--with-nth=2..", "--nth=2..",
               "--no-sort", "--tiebreak=index", "--prompt", prompt, "--header", header,
               "--query", query, "--bind=ctrl-j:down,ctrl-k:up",
               "--expect=" + ("ctrl-a,ctrl-d,ctrl-o,alt-f,alt-h,ctrl-r" if switches else "enter")]
    if multiple:
        command.append("--multi")
    if preview_command:
        command.extend(["--preview", preview_command,
                        "--preview-window=right:50%:wrap:<100(down:45%:wrap)",
                        "--bind=ctrl-p:toggle-preview"])
    env = dict(os.environ, FZF_DEFAULT_OPTS="", FZF_DEFAULT_OPTS_FILE="")
    result = subprocess.run(command, input=b"".join(row.encode("utf-8") + b"\0" for row in rows),
                            stdout=subprocess.PIPE, env=env)
    if result.returncode == 130:
        return None
    if result.returncode not in (0, 1):
        raise RuntimeError(f"fzf exited with status {result.returncode}")
    parts = result.stdout.decode("utf-8").split("\0")
    if len(parts) < 3:
        return None
    return parts[0], parts[1], [row.split("\t", 1)[0] for row in parts[2:] if row]


def choose_folder(entries, current):
    counts = Counter()
    for entry in entries:
        for parent in Path(entry["path"]).parents:
            if parent == Path("/"):
                break
            counts[parent] += 1
    folders = sorted(counts, key=lambda p: str(p).casefold())
    rows = [f"{i}\t{counts[p]:4} PDFs\t{clean(label(p)).replace(chr(10), ' ')}"
            for i, p in enumerate(folders)]
    result = choose(rows, "Folder > ", "Enter: restrict to folder and subfolders · Esc: back",
                    query="" if current is None else str(current.name), switches=False)
    return folders[int(result[2][0])] if result and result[2] else current


def pick(args):
    roots = search_roots(args.roots)
    if args.roots and any(not p.is_dir() for p in roots):
        raise RuntimeError("Every search root must be an existing folder")
    downloads = downloads_directory()
    if not args.roots and downloads.is_dir():
        roots.append(downloads)
    entries = scan(roots, args.all, include_history=not args.roots)
    recent = history()
    if args.list:
        for entry in view_entries(entries, args.view, None, downloads, recent):
            print(entry["path"])
        return
    view, folder, query = args.view, None, args.query
    with tempfile.TemporaryDirectory(prefix="pdfpick-") as temporary:
        index_file = Path(temporary) / "index.json"
        while True:
            visible = view_entries(entries, view, folder, downloads, recent)
            index_file.write_text(json.dumps(visible))
            rows = []
            for i, entry in enumerate(visible):
                path = Path(entry["path"])
                stamp = recent[entry["path"]] if view == "opened" else entry["added"]
                name = clean(path.name).replace("\n", " ")
                parent = clean(label(path.parent)).replace("\n", " ")
                rows.append(f"{i}\t{date(stamp)}\t{name}\t{parent}")
            header = (f"{VIEWS[view]} · {clean(label(folder)) if folder else 'all folders'}\n"
                      "Ctrl+A All · Ctrl+D Downloads · Ctrl+O Opened · Alt+F Folder · Alt+H Clear folder\n"
                      "Enter Open · Tab Mark · Ctrl+P Preview · Ctrl+R Refresh · Esc Quit")
            preview_command = shlex.join([sys.executable, str(Path(__file__).resolve()),
                                           "--preview", str(index_file)]) + " {1}"
            result = choose(rows, "PDF > ", header, query, preview_command, multiple=True)
            if result is None:
                return
            query, key, selected = result
            if key in ("ctrl-a", "ctrl-d", "ctrl-o"):
                view = {"ctrl-a": "all", "ctrl-d": "downloads", "ctrl-o": "opened"}[key]
            elif key == "alt-f":
                folder = choose_folder(entries, folder)
            elif key == "alt-h":
                folder = None
            elif key == "ctrl-r":
                entries = scan(roots, args.all, include_history=not args.roots)
                recent = history()
            elif selected:
                paths = [visible[int(i)]["path"] for i in selected]
                if args.print:
                    print("\n".join(paths))
                else:
                    subprocess.run(["zathura", "--fork", "--", *paths], check=True,
                                   stdin=subprocess.DEVNULL)
                    record_opened(paths)
                return


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("roots", nargs="*", help="Folders to search (default: home)")
    parser.add_argument("--view", choices=VIEWS, default="all")
    parser.add_argument("--query", default="")
    parser.add_argument("--all", action="store_true", help="Include hidden and generated folders")
    parser.add_argument("--print", action="store_true", help="Print selection instead of opening")
    parser.add_argument("--list", action="store_true", help="List PDFs without opening the picker")
    parser.add_argument("--preview", nargs=2, help=argparse.SUPPRESS)
    args = parser.parse_args()
    try:
        if args.preview:
            preview(*args.preview)
        else:
            pick(args)
    except (OSError, ValueError, RuntimeError, sqlite3.Error, subprocess.SubprocessError) as error:
        print(f"pdfpick: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
