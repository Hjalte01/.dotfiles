"""Offline gateway tests; fake listeners never authenticate an SSH account."""
from contextlib import contextmanager
import shlex
import socket
import subprocess
import threading
import time
import unittest
from unittest.mock import patch

from hendrix import core, gateway


@contextmanager
def fake_gateway(address='127.0.0.1', port=0, greeting=b'SSH-2.0-TestServer\r\n', *, silent=False):
    stop = threading.Event()
    client_greetings = []
    family = socket.AF_INET6 if ':' in address else socket.AF_INET
    with socket.socket(family, socket.SOCK_STREAM) as listener:
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind((address, port))
        listener.listen()
        listener.settimeout(.1)

        def serve():
            try:
                while not stop.is_set():
                    try:
                        connection, _ = listener.accept()
                    except socket.timeout:
                        continue
                    with connection:
                        connection.settimeout(.5)
                        data = b''
                        while b'\n' not in data and len(data) < 1024:
                            chunk = connection.recv(1024)
                            if not chunk:
                                break
                            data += chunk
                        client_greetings.append(data)
                        if silent:
                            stop.wait(2)
                        else:
                            connection.sendall(greeting)
            except OSError:
                pass

        worker = threading.Thread(target=serve, daemon=True)
        worker.start()
        try:
            yield listener.getsockname()[1], client_greetings
        finally:
            stop.set()
            worker.join(1)


class GatewayTests(unittest.TestCase):
    config = dict(user='fhz806', hostname='hendrixgate', port='22', addressfamily='any')

    def dns(self, addresses):
        output = ''.join(f'{address} STREAM hendrixgate\n{address} DGRAM\n' for address in addresses)
        return subprocess.CompletedProcess([], 0, output, '')

    def test_silent_first_gateway_uses_responsive_dns_alternative_without_authentication(self):
        with fake_gateway('127.0.0.1', silent=True) as (port, silent_received), \
             fake_gateway('127.0.0.2', port) as (_, ready_received), \
             patch.object(gateway.subprocess, 'run', return_value=self.dns(['127.0.0.1', '127.0.0.2'])) as dns, \
             patch.object(gateway.shutil, 'which', return_value='/nix/store/netcat/bin/nc'), \
             patch.object(gateway, 'PROBE_TIMEOUT', .2):
            started = time.monotonic()
            options = gateway.gateway_options(dict(self.config, port=str(port)))
            elapsed = time.monotonic() - started
            self.assertLess(elapsed, .8)
            self.assertEqual(shlex.split(options[1].split('=', 1)[1]),
                             ['/nix/store/netcat/bin/nc', '-F', '-w', '8', '127.0.0.2', str(port)])
            self.assertEqual(options[2:], ['-o', 'ProxyUseFdpass=yes'])
            self.assertNotIn('HostName=', ' '.join(options))
            self.assertEqual(silent_received, [gateway.CLIENT_GREETING])
            self.assertEqual(ready_received, [gateway.CLIENT_GREETING])
            dns.assert_called_once_with(['getent', 'ahosts', 'hendrixgate'], capture_output=True,
                                        text=True, timeout=5)

    def test_multiple_healthy_gateways_preserve_dns_order(self):
        with fake_gateway('127.0.0.1') as (port, _), \
             fake_gateway('127.0.0.2', port) as (_, _), \
             patch.object(gateway.subprocess, 'run', return_value=self.dns(['127.0.0.2', '127.0.0.1'])), \
             patch.object(gateway.shutil, 'which', return_value='/bin/nc'):
            options = gateway.gateway_options(dict(self.config, port=str(port)))
        self.assertEqual(shlex.split(options[1].split('=', 1)[1])[-2:], ['127.0.0.2', str(port)])

    def test_no_responding_gateway_fails_with_bounded_actionable_diagnostic(self):
        with fake_gateway(silent=True) as (port, _), \
             patch.object(gateway.subprocess, 'run', return_value=self.dns(['127.0.0.1'])), \
             patch.object(gateway.shutil, 'which', return_value='/bin/nc'), \
             patch.object(gateway, 'PROBE_TIMEOUT', .1):
            with self.assertRaisesRegex(core.Error, 'No Hendrix SSH gateway.*KU VPN'):
                gateway.gateway_options(dict(self.config, port=str(port)))

    def test_unexpected_account_host_and_custom_transport_are_untouched(self):
        changes = [dict(user='other'), dict(hostname='other.example'),
                   dict(proxycommand='ssh jump -W %h:%p'), dict(proxycommand='*'), dict(proxyjump='jump'),
                   dict(canonicalizehostname='yes'), dict(canonicalizehostname='always'),
                   dict(bindaddress='192.0.2.1'), dict(bindinterface='custom0')]
        for changed in changes:
            with self.subTest(changed=changed), \
                 patch.object(gateway.subprocess, 'run', side_effect=AssertionError('Unexpected DNS lookup')), \
                 patch.object(gateway.shutil, 'which', side_effect=AssertionError('Unexpected transport lookup')):
                self.assertEqual(gateway.gateway_options(dict(self.config, **changed)), [])

    def test_dns_filters_duplicates_malformed_addresses_and_requested_family(self):
        result = self.dns(['192.0.2.1', '2001:db8::1', '192.0.2.1', 'unsafe;command'])
        with patch.object(gateway.subprocess, 'run', return_value=result):
            self.assertEqual(gateway._addresses('hendrixgate', 'any'), ['192.0.2.1', '2001:db8::1'])
            self.assertEqual(gateway._addresses('hendrixgate', 'inet'), ['192.0.2.1'])
            self.assertEqual(gateway._addresses('hendrixgate', 'inet6'), ['2001:db8::1'])

    @unittest.skipUnless(socket.has_ipv6, 'IPv6 sockets are unavailable')
    def test_ipv6_gateway_uses_numeric_address_and_safely_quoted_netcat_path(self):
        with fake_gateway('::1') as (port, received), \
             patch.object(gateway.subprocess, 'run', return_value=self.dns(['::1'])), \
             patch.object(gateway.shutil, 'which', return_value='/tools with spaces/nc'):
            options = gateway.gateway_options(dict(self.config, port=str(port), addressfamily='inet6'))
        self.assertEqual(shlex.split(options[1].split('=', 1)[1]),
                         ['/tools with spaces/nc', '-F', '-w', '8', '::1', str(port)])
        self.assertEqual(received, [gateway.CLIENT_GREETING])

    def test_dns_failure_and_timeout_have_useful_errors(self):
        with patch.object(gateway.subprocess, 'run', side_effect=subprocess.TimeoutExpired('getent', 5)):
            with self.assertRaisesRegex(core.Error, 'DNS lookup timed out.*KU VPN'):
                gateway._addresses('hendrixgate', 'any')
        with patch.object(gateway.subprocess, 'run', return_value=subprocess.CompletedProcess([], 2, '', '')):
            with self.assertRaisesRegex(core.Error, 'DNS is unavailable.*KU VPN'):
                gateway._addresses('hendrixgate', 'any')

    def test_only_complete_valid_ssh_greetings_are_accepted(self):
        cases = [(b'Welcome\r\nSSH-2.0-TestServer with comments\r\n', True),
                 (b'SSH-1.99-TestServer\n', True),
                 (b'SSH-2.0-TestServer', False), (b'SSH-1.5-TestServer\r\n', False),
                 (b'SSH-2.0-\r\n', False), (b'HTTP/1.1 200 OK\r\n', False),
                 (b'SSH-2.0-' + b'x' * 255 + b'\r\n', False)]
        for greeting, expected in cases:
            with self.subTest(greeting=greeting[:40]), fake_gateway(greeting=greeting) as (port, received):
                ready = gateway._ssh_banner('127.0.0.1', port, time.monotonic() + .3)
                self.assertEqual(ready, expected)
                self.assertEqual(received, [gateway.CLIENT_GREETING])

    def test_excessive_pre_banner_data_is_bounded(self):
        greeting = b'x' * gateway.MAX_BANNER_BYTES + b'\nSSH-2.0-TestServer\r\n'
        with fake_gateway(greeting=greeting) as (port, _):
            self.assertFalse(gateway._ssh_banner('127.0.0.1', port, time.monotonic() + .3))

    def test_invalid_ports_fail_before_any_network_probe(self):
        for port in ['not-a-port', '0', '-1', '65536']:
            with self.subTest(port=port), patch.object(gateway.subprocess, 'run') as dns:
                with self.assertRaisesRegex(core.Error, 'SSH port is invalid'):
                    gateway.gateway_options(dict(self.config, port=port))
                dns.assert_not_called()


if __name__ == '__main__':
    unittest.main()
