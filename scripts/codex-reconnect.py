#!/usr/bin/env python3
"""Drop pre-sleep Codex HTTPS sockets while systemd keeps users frozen."""

import argparse
import ipaddress
from pathlib import Path
import re
import subprocess
from typing import NamedTuple


FROZEN_EVENTS = Path('/sys/fs/cgroup/user.slice/cgroup.events')


class Connection(NamedTuple):
    local: str
    local_port: int
    peer: str
    peer_port: int
    family: str
    pid: int
    fd: int
    inode: str


def endpoint(value):
    host, port = value.rsplit(':', 1)
    address = ipaddress.ip_address(host.strip('[]'))
    number = int(port)
    if not 0 < number <= 65535:
        raise ValueError('invalid port')
    return address, number


def owned_by_codex(connection, proc=Path('/proc')):
    """Recheck the actual executable, cgroup and descriptor, not ss's label."""
    process = proc / str(connection.pid)
    try:
        groups = [line.split(':', 2)[2]
                  for line in (process / 'cgroup').read_text().splitlines()]
        return ((process / 'exe').readlink().name == 'codex'
                and any(group.startswith('/user.slice/') for group in groups)
                and str((process / 'fd' / str(connection.fd)).readlink())
                == f'socket:[{connection.inode}]')
    except (OSError, ValueError, IndexError):
        return False


def connections(output, proc=Path('/proc')):
    for line in output.splitlines():
        fields = line.split(None, 5)
        if len(fields) != 6 or fields[0] != 'ESTAB':
            continue
        try:
            local, local_port = endpoint(fields[3])
            peer, peer_port = endpoint(fields[4])
        except ValueError:
            continue
        public_peer = getattr(peer, 'ipv4_mapped', None) or peer
        inode = re.search(r'\bino:(\d+)\b', fields[5])
        if peer_port != 443 or not public_peer.is_global or not inode:
            continue
        if local.version != peer.version:
            continue
        for pid, fd in re.findall(r'\bpid=(\d+),fd=(\d+)\b', fields[5]):
            connection = Connection(str(local), local_port, str(peer), peer_port,
                                    f'-{local.version}', int(pid), int(fd), inode[1])
            if owned_by_codex(connection, proc):
                yield connection
                break


def users_frozen():
    try:
        return 'frozen 1' in FROZEN_EVENTS.read_text().splitlines()
    except OSError:
        return False


def reset_command(ss, connection):
    local = f'[{connection.local}]' if connection.family == '-6' else connection.local
    peer = f'[{connection.peer}]' if connection.family == '-6' else connection.peer
    return [ss, '-K', '-t', connection.family,
            f'src {local} sport = :{connection.local_port} '
            f'dst {peer} dport = :{connection.peer_port}']


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ss', required=True, help='absolute path to iproute2 ss')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--apply', action='store_true', help='reset sockets; users must be frozen')
    mode.add_argument('--dry-run', action='store_true', help='only count eligible sockets (default)')
    args = parser.parse_args(argv)
    if not Path(args.ss).is_absolute():
        parser.error('--ss must be an absolute path')
    if args.apply and not users_frozen():
        print('codex-reconnect: skipped; user.slice is not frozen', flush=True)
        return 0
    try:
        listing = subprocess.run([args.ss, '-Htnpe', '( dport = :443 )'],
                                 check=True, capture_output=True, text=True, timeout=5)
        candidates = list(connections(listing.stdout))
        reset = 0
        if args.apply:
            for connection in candidates:
                if not users_frozen():
                    raise RuntimeError('user.slice thawed; stopping socket resets')
                if owned_by_codex(connection):
                    subprocess.run(reset_command(args.ss, connection), check=True,
                                   capture_output=True, text=True, timeout=3)
                    reset += 1
        print(f'codex-reconnect: {reset} reset; {len(candidates)} eligible HTTPS sockets',
              flush=True)
        return 0
    except (OSError, subprocess.SubprocessError, RuntimeError) as error:
        print(f'codex-reconnect: {error}', flush=True)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
