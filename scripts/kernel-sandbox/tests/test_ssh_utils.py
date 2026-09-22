import contextlib
import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path

import libs.ssh_utils as ssh_utils
from libs.ssh_utils import build_ssh_command, connect_ssh_and_wait, wait_for_ssh_ready


@contextlib.contextmanager
def mock_socket_bind():
    """binds to localhost TCP socket on an OS-assigned free port without
    listening yet, so its port number is reserved and known but connecting
    to it fails until the caller starts accepting"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    try:
        yield sock, sock.getsockname()[1]
    finally:
        sock.close()


def _serve_once(sock, response_bytes, accept_delay=0):
    """Accepts exactly one real connection on an already-listening socket and
    writes response_bytes (ex: SSH-2.0 banner) to it, optionally after a short delay to simulate
    a guest OS that isn't up yet."""
    def _run():
        if accept_delay:
            time.sleep(accept_delay)
        try:
            sock.listen(1)
            conn, _ = sock.accept()
            with conn:
                if response_bytes:
                    conn.sendall(response_bytes)
        except OSError:
            pass

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return thread


class TestWaitForSshReady(unittest.TestCase):
    def test_returns_true_when_real_ssh_banner_received(self):
        with mock_socket_bind() as (sock, port):
            sock.listen(1)
            thread = _serve_once(sock, b"SSH-2.0-OpenSSH_10.0\r\n")
            self.assertTrue(wait_for_ssh_ready(
                port=port, host="127.0.0.1", timeout=5, socket_timeout=0.3, settle_delay=0.05))
            thread.join(timeout=5)

    def test_returns_false_on_real_connection_refused(self):
        """nothing listening on the port at all - ConnectionRefusedError"""
        with mock_socket_bind() as (_sock, port):
            pass  # socket closed, port becomes free again - ConnectionRefused
        self.assertFalse(wait_for_ssh_ready(
            port=port, host="127.0.0.1", timeout=0.3, poll_interval=0.05, socket_timeout=0.1))

    def test_retries_until_ssh_server_comes_up(self):
        """the guest isn't listening yet for the first moment, then comes up - must retry rather than giving up on first refusal."""
        with mock_socket_bind() as (sock, port):
            sock.listen(1)
            thread = _serve_once(sock, b"SSH-2.0-OpenSSH_10.0\r\n", accept_delay=0.2)
            self.assertTrue(wait_for_ssh_ready(
                port=port, host="127.0.0.1", timeout=5, poll_interval=0.05,
                socket_timeout=0.3, settle_delay=0.05))
            thread.join(timeout=5)

    def test_returns_false_when_response_banner_never_arrives(self):
        """something is listening and accepts, but never sends a SSH banner (ex. SSH-2.0-)"""
        with mock_socket_bind() as (sock, port):
            sock.listen(1)
            thread = _serve_once(sock, b"")
            self.assertFalse(wait_for_ssh_ready(
                port=port, host="127.0.0.1", timeout=0.3, poll_interval=0.05, socket_timeout=0.1))
            thread.join(timeout=5)


class TestBuildSshCommand(unittest.TestCase):
    def test_command_shape(self):
        cmd = build_ssh_command(port=2222, host="localhost")
        self.assertEqual(cmd[0], "ssh")
        self.assertEqual(cmd[cmd.index("-p") + 1], "2222")
        self.assertIn("root@localhost", cmd)
        self.assertIn("StrictHostKeyChecking=no", cmd)


class TestConnectSshAndWait(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self._original_run = ssh_utils.subprocess.run

    def tearDown(self):
        ssh_utils.subprocess.run = self._original_run
        self.tmpdir.cleanup()

    def _make_mock_ssh(self, script_body):
        script = Path(self.tmpdir.name) / "mock-ssh"
        script.write_text(f"#!/bin/sh\n{script_body}\n")
        script.chmod(0o755)
        return str(script)

    def test_clean_exit_returns_true(self):
        mock_ssh = self._make_mock_ssh("exit 0")
        self.assertTrue(connect_ssh_and_wait(port=2222, host="localhost", ssh_bin=mock_ssh))

    def test_nonzero_exit_returns_false_regression(self):
        """a real failed/refused SSH connection (nonzero exit) must be reported as failure"""
        mock_ssh = self._make_mock_ssh("exit 255")
        self.assertFalse(connect_ssh_and_wait(port=2222, host="localhost", ssh_bin=mock_ssh))

    def test_keyboard_interrupt_is_handled_gracefully(self):
        def _raise_keyboard_interrupt(*args, **kwargs):
            raise KeyboardInterrupt()
        ssh_utils.subprocess.run = _raise_keyboard_interrupt
        self.assertFalse(connect_ssh_and_wait(port=2222, host="localhost"))

    def test_unexpected_exception_is_handled_gracefully(self):
        def _raise_os_error(*args, **kwargs):
            raise OSError("ssh binary missing")
        ssh_utils.subprocess.run = _raise_os_error
        self.assertFalse(connect_ssh_and_wait(port=2222, host="localhost"))
