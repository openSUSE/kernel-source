"""
Virtual machine SSH connectivity utils - polling for a booted guest's SSH
daemon and handing off to an interactive ssh session.
"""
import socket
import subprocess
import time

from libs.console import get_logger, print_phase_header

logger = get_logger(__name__)


def wait_for_ssh_ready(port=2222, host="localhost", timeout=300, poll_interval=2, socket_timeout=2, settle_delay=1):
    logger.info(f"Waiting for SSH on {host}:{port} (timeout: {timeout}s)...")
    start_time = time.time()
    next_log_time = start_time + 10

    while (time.time() - start_time) < timeout:
        try:
            with socket.create_connection((host, port), timeout=socket_timeout) as s:
                s.settimeout(socket_timeout)
                banner = s.recv(1024)
                if banner.startswith(b"SSH-"):
                    logger.info(f"SSH daemon is fully booted and responding on {port}")
                    time.sleep(settle_delay)
                    return True
        except (socket.timeout, ConnectionRefusedError, OSError, ConnectionResetError):
            pass

        current_time = time.time()
        if current_time > next_log_time:
            logger.info(f"Still waiting for guest OS to boot and start SSH on {port}...")
            next_log_time = current_time + 10
        time.sleep(poll_interval)

    logger.warning(f"SSH port did not respond within {timeout}s")
    return False


def build_ssh_command(port=2222, host="localhost", ssh_bin="ssh"):
    return [
        ssh_bin,
        "-p", str(port),
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        "-o", "LogLevel=ERROR",
        f"root@{host}"
    ]


def connect_ssh_and_wait(port=2222, host="localhost", ssh_bin="ssh"):
    ssh_cmd = build_ssh_command(port, host, ssh_bin=ssh_bin)

    print_phase_header(
        phase_title=f"Sandbox active! Connecting via: ssh -p {port} root@{host}",
    )

    try:
        res = subprocess.run(ssh_cmd)
        if res.returncode != 0:
            logger.warning(f"SSH session exited with code {res.returncode}")
            return False
        logger.info("SSH session ended")
        return True
    except KeyboardInterrupt:
        logger.info("SSH session interrupted by user")
        return False
    except Exception as e:
        logger.exception(f"SSH session failed with error: {e}")
        return False
