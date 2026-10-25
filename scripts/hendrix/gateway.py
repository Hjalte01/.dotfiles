"""Choose a responsive KU SSH gateway before attempting account authentication."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import ipaddress
from pathlib import Path
import re
import shlex
import shutil
import socket
import subprocess
import time

from .core import Error

DNS_TIMEOUT = 5
PROBE_TIMEOUT = 5
MAX_BANNER_BYTES = 8192
CLIENT_GREETING = b'SSH-2.0-HendrixGatewayProbe\r\n'
SERVER_GREETING = re.compile(rb'SSH-(?:2\.0|1\.99)-[!-~]+(?: [ -~]*)?\r?\n')


def _direct_ku_config(config):
    if (config.get('user') != 'fhz806' or config.get('hostname') not in
            ('hendrixgate', 'hendrixgate.science.ku.dk')):
        return False
    # A configured transport, source interface or canonicalization remains the
    # user's responsibility; replacing it could connect through another route.
    for option in ('proxycommand', 'proxyjump', 'bindaddress', 'bindinterface'):
        if config.get(option, 'none').lower() not in ('', 'none'):
            return False
    if config.get('canonicalizehostname', 'false').lower() not in ('no', 'false'):
        return False
    return config.get('addressfamily', 'any') in ('any', 'inet', 'inet6')


def _addresses(hostname, family):
    try:
        result = subprocess.run(['getent', 'ahosts', hostname], capture_output=True,
                                text=True, timeout=DNS_TIMEOUT)
    except subprocess.TimeoutExpired as exc:
        raise Error('Hendrix gateway DNS lookup timed out. Check your KU VPN and retry Connect.') from exc
    except OSError as exc:
        raise Error(f'Could not resolve Hendrix SSH gateways: {exc}') from exc
    addresses = []
    for line in (result.stdout or '').splitlines():
        fields = line.split()
        if not fields:
            continue
        try:
            address = ipaddress.ip_address(fields[0])
        except ValueError:
            continue
        if (family == 'inet' and address.version != 4 or
                family == 'inet6' and address.version != 6):
            continue
        value = str(address)
        if value not in addresses:
            addresses.append(value)
    if result.returncode or not addresses:
        raise Error('Hendrix gateway DNS is unavailable. Check your KU VPN and retry Connect.')
    return addresses


def _ssh_banner(address, port, deadline):
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        return False
    family = socket.AF_INET6 if ipaddress.ip_address(address).version == 6 else socket.AF_INET
    try:
        with socket.socket(family, socket.SOCK_STREAM) as connection:
            connection.settimeout(remaining)
            connection.connect((address, port))
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            connection.settimeout(remaining)
            # Identification exchange contains no username, password or MFA.
            # Sending our greeting also supports servers that wait for a client.
            connection.sendall(CLIENT_GREETING)
            buffered = b''
            received = 0
            while received < MAX_BANNER_BYTES:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                connection.settimeout(remaining)
                chunk = connection.recv(min(1024, MAX_BANNER_BYTES - received))
                if not chunk:
                    return False
                received += len(chunk)
                buffered += chunk
                while b'\n' in buffered:
                    line, buffered = buffered.split(b'\n', 1)
                    line += b'\n'
                    if line.startswith(b'SSH-'):
                        return len(line) <= 255 and SERVER_GREETING.fullmatch(line) is not None
    except (OSError, ValueError):
        return False
    return False


def gateway_options(config):
    """Keep SSH's logical hostname while connecting to a healthy DNS endpoint."""
    if not _direct_ku_config(config):
        return []
    try:
        port = int(config.get('port', '22'))
    except (TypeError, ValueError) as exc:
        raise Error('The configured Hendrix SSH port is invalid.') from exc
    if not 1 <= port <= 65535:
        raise Error('The configured Hendrix SSH port is invalid.')
    netcat = shutil.which('nc')
    if not netcat:
        raise Error('Hendrix gateway selection needs nc. Rebuild the Hendrix package and retry.')
    addresses = _addresses(config['hostname'], config.get('addressfamily', 'any'))
    deadline = time.monotonic() + PROBE_TIMEOUT
    # All endpoints share one deadline, including any queued work. A silent
    # gateway therefore cannot consume another timeout for each DNS address.
    with ThreadPoolExecutor(max_workers=min(8, len(addresses))) as executor:
        responsive = list(executor.map(lambda address: _ssh_banner(address, port, deadline), addresses))
    selected = next((address for address, ready in zip(addresses, responsive) if ready), None)
    if selected is None:
        raise Error('No Hendrix SSH gateway answered with a valid SSH greeting within '
                    f'{PROBE_TIMEOUT:g} seconds. The KU VPN may be connected while the '
                    'gateways are unavailable; retry Connect or check hendrix status.')
    # -F transfers the connected socket and exits. Consequently -w bounds only
    # connection setup; it cannot interrupt an otherwise idle SSH control master.
    command = shlex.join([str(Path(netcat).absolute()), '-F', '-w', '8', selected, str(port)])
    return ['-o', 'ProxyCommand=' + command, '-o', 'ProxyUseFdpass=yes']
