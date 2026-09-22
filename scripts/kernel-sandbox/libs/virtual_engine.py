import shlex
import subprocess
import time
from libs.errors import KernelSandboxError


class VirtualEngineError(KernelSandboxError):
    pass


class VirtualMachine:
    def __init__(
            self, qemu_bin, arch, ram="4096", smp="4", disk_path=None, network_maps=None, extra_qemu_args="",
            enable_kvm=False, kernel=None, initrd=None, append=None, append_extra=None, fsdevs=None,
            machine_cpu_console_profile=None):
        self.qemu_bin = qemu_bin
        self.arch = arch
        self.ram = ram
        self.smp = smp
        self.disk_path = disk_path
        self.network_maps = network_maps or []
        self.extra_qemu_args = extra_qemu_args
        self.enable_kvm = enable_kvm
        self.kernel = kernel
        self.initrd = initrd
        self.append = append
        self.append_extra = append_extra
        self.fsdevs = fsdevs or []
        self.proc = None
        self.log_fd = None
        self.profile = machine_cpu_console_profile  # ref: qemu_arch_profiles

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.teardown()

    def build_command(self):
        cmd = [self.qemu_bin]
        if self.profile is not None:
            cpu_type = self.profile["cpu_kvm"] if self.enable_kvm else self.profile["cpu_tcg"]
            cmd.extend(["-machine", f"{self.profile['machine']}{self.profile.get('machine_args', '')}"])
            cmd.extend(["-cpu", cpu_type])

        cmd.extend([
            "-m", str(self.ram),
            "-smp", str(self.smp),
            "-nographic",
            "-no-reboot",
            "-object", "rng-random,filename=/dev/urandom,id=rng0",
            "-device", "virtio-rng-pci,rng=rng0",
        ])

        for netdev, device in self.network_maps:
            cmd.extend(["-netdev", netdev, "-device", device])

        if self.enable_kvm:
            cmd.append("-enable-kvm")

        if self.disk_path:
            cmd.extend(["-drive", f"file={self.disk_path},format=qcow2,if=virtio"])

        if self.kernel:
            cmd.extend(["-kernel", str(self.kernel)])
            if self.append:
                append_str = self.append
            elif self.profile is not None:
                append_str = f"console={self.profile['console']} root=/dev/ram0 ip=dhcp panic=1"
            else:
                append_str = "root=/dev/ram0 ip=dhcp panic=1"
            if self.append_extra:
                append_str += f" {self.append_extra}"
            cmd.extend(["-append", append_str])
        if self.initrd:
            cmd.extend(["-initrd", str(self.initrd)])

        for fsdev, device in self.fsdevs:
            cmd.extend(["-fsdev", fsdev, "-device", device])

        if self.extra_qemu_args:
            cmd.extend(shlex.split(self.extra_qemu_args))

        return cmd

    def spawn(self, log_fd=None, stdin_dest=subprocess.DEVNULL, stdout_dest=subprocess.PIPE, stderr_dest=subprocess.PIPE):
        """Starts the QEMU process. When log_fd is given it receives both
        stdout and stderr (a single combined log file); stdout_dest/stderr_dest
        are only used when log_fd is not provided."""
        cmd = self.build_command()
        target_out = log_fd if log_fd is not None else stdout_dest
        target_err = log_fd if log_fd is not None else stderr_dest
        self.log_fd = log_fd

        self.proc = subprocess.Popen(
            cmd,
            stdout=target_out,
            stderr=target_err,
            stdin=stdin_dest,
            text=True
        )
        return self.proc

    def _read_crash_diagnostics(self):
        """extract crash output. self.proc.stderr is only populated when
        spawn() used stderr_dest=PIPE; when a combined log_fd was used
        instead, proc.stderr is None, so fall back to reading the log file."""
        if self.proc.stderr and not self.proc.stderr.closed:
            return self.proc.stderr.read().strip()
        if self.log_fd is not None and not self.log_fd.closed:
            try:
                self.log_fd.seek(0)
                return self.log_fd.read().strip()
            except (OSError, ValueError):
                return ""
        return ""

    def verify_health(self, delay=1.0):
        """Check if the QEMU process crashed immediately after spawning."""
        if not self.proc:
            return False
        time.sleep(delay)
        if self.proc.poll() is not None:
            stderr_output = self._read_crash_diagnostics()
            raise VirtualEngineError(
                f"QEMU process died unexpectedly (Exit: {self.proc.returncode}).Stderr: {stderr_output}")
        return True

    def teardown(self, timeout=5):
        """teardown the hypervisor process when context closes."""
        if self.proc and self.proc.poll() is None:  # still running
            self.proc.terminate()
            try:
                self.proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()
        self._close_pipes()

    def _close_pipes(self):
        """Closes any PIPE-backed stdout/stderr/stdin file objects left open on a finished process"""
        if not self.proc:
            return
        for stream in (self.proc.stdout, self.proc.stderr, self.proc.stdin):
            if stream and not stream.closed:
                stream.close()
