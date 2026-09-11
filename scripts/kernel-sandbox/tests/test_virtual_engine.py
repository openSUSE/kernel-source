import subprocess
import sys
import tempfile
import unittest

from libs.virtual_engine import VirtualEngineError, VirtualMachine

X86_64_PROFILE = {"machine": "q35", "machine_args": "", "cpu_kvm": "host", "cpu_tcg": "max", "console": "ttyS0"}
AARCH64_PROFILE = {"machine": "virt", "machine_args": ",gic-version=max", "cpu_kvm": "host", "cpu_tcg": "max", "console": "ttyAMA0"}


def _mock_qemu_exec(python_code):
    """mock qemu exec behavior, the stdout/stderr part of it"""
    return [sys.executable, "-c", python_code]


class TestBuildCommand(unittest.TestCase):
    def test_default_x86_64_command_generation(self):
        """Verify the standard x86_64 TCG build string matches expectations."""
        vm = VirtualMachine(
            qemu_bin="qemu-system-x86_64",
            arch="x86_64",
            machine_cpu_console_profile=X86_64_PROFILE,
            kernel="/boot/vmlinuz",
            initrd="/boot/initrd"
        )
        cmd = vm.build_command()

        # Check binary choice and arch_profiles
        self.assertEqual(cmd[0], "qemu-system-x86_64")
        self.assertIn("-machine", cmd)
        self.assertEqual(cmd[cmd.index("-machine") + 1], "q35")
        self.assertIn("-cpu", cmd)
        self.assertEqual(cmd[cmd.index("-cpu") + 1], "max")  # fallsback to cpu_tcg max since enable_kvm=False

        # Check console setup
        append_idx = cmd.index("-append")
        self.assertIn("console=ttyS0", cmd[append_idx + 1])

    def test_kvm_acceleration_cpu_assignment(self):
        """Ensure CPU model switches to host when KVM is enabled."""
        vm = VirtualMachine(
            qemu_bin="qemu-system-x86_64",
            arch="x86_64",
            machine_cpu_console_profile=X86_64_PROFILE,
            enable_kvm=True
        )
        cmd = vm.build_command()
        self.assertEqual(cmd[cmd.index("-cpu") + 1], "host")
        self.assertIn("-enable-kvm", cmd)

    def test_cross_arch_profile_mapping_aarch64(self):
        """Verify cros-compiling targets like arm."""
        vm = VirtualMachine(
            qemu_bin="qemu-system-aarch64",
            arch="aarch64",
            machine_cpu_console_profile=AARCH64_PROFILE,
            kernel="/boot/Image"
        )
        cmd = vm.build_command()

        # verify machine and console targets.
        self.assertEqual(cmd[cmd.index("-machine") + 1], "virt,gic-version=max")
        append_idx = cmd.index("-append")
        self.assertIn("console=ttyAMA0", cmd[append_idx + 1])

    def test_no_profile_omits_machine_and_cpu_flags(self):
        """An arch without a kernel_sandbox_profiles.yaml entry (ex: mips)
        qemu-system-<arch> already has sensible built-in defaults when -machine/-cpu are omitted."""
        vm = VirtualMachine(qemu_bin="qemu-system-mips", arch="mips", kernel="/boot/vmlinux-mips")
        cmd = vm.build_command()
        self.assertNotIn("-machine", cmd)
        self.assertNotIn("-cpu", cmd)
        append_idx = cmd.index("-append")
        self.assertNotIn("console=", cmd[append_idx + 1])
        self.assertIn("root=/dev/ram0", cmd[append_idx + 1])

    def test_no_profile_still_honors_explicit_append(self):
        vm = VirtualMachine(
            qemu_bin="qemu-system-mips", arch="mips", kernel="/boot/vmlinux-mips",
            append="console=ttyS0,115200 root=/dev/sda1")
        cmd = vm.build_command()
        append_idx = cmd.index("-append")
        self.assertEqual(cmd[append_idx + 1], "console=ttyS0,115200 root=/dev/sda1")

    def test_extra_qemu_args_and_device_mappings(self):
        """Assert multi args with extra_qemu_args and device mappings."""
        vm = VirtualMachine(
            qemu_bin="qemu-system-x86_64",
            arch="x86_64",
            disk_path="/var/lib/image.qcow2",
            network_maps=[("tap,id=net0", "virtio-net-pci,netdev=net0")],
            extra_qemu_args="-snapshot -device usb-device"
        )
        cmd = vm.build_command()
        join_cmd = " ".join(cmd)

        # verify drive
        self.assertIn("-drive file=/var/lib/image.qcow2,format=qcow2,if=virtio", join_cmd)

        # verify netdev and device mappings via network_maps
        self.assertIn("-netdev tap,id=net0", join_cmd)
        self.assertIn("-device virtio-rng-pci,rng=rng0", join_cmd)
        self.assertIn("-device virtio-net-pci,netdev=net0", join_cmd)

        # verify qemu_extra_args
        self.assertIn("-snapshot -device usb-device", join_cmd)

    def test_no_kernel_omits_append_and_initrd(self):
        """without a kernel path, -append/-initrd must not appear (booting from disk_path instead)."""
        vm = VirtualMachine(qemu_bin="qemu-system-x86_64", arch="x86_64", disk_path="/var/lib/image.qcow2")
        cmd = vm.build_command()
        self.assertNotIn("-append", cmd)
        self.assertNotIn("-initrd", cmd)


class TestSetup(unittest.TestCase):
    """Shared setUp/tearDown for tests"""
    def setUp(self):
        self.vm = None

    def tearDown(self):
        if self.vm and self.vm.proc:
            self.vm.teardown(timeout=1)


class TestSpawn(TestSetup):
    def test_default_pipes_capture_real_output(self):
        """default stdout_dest/stderr_dest=PIPE captures the child's real stdout and stderr independently."""
        self.vm = VirtualMachine(qemu_bin="qemu-system-x86_64", arch="x86_64")
        self.vm.build_command = lambda: _mock_qemu_exec(
            "import sys; print('hello-stdout'); print('hello-stderr', file=sys.stderr)"
        )
        self.vm.spawn()
        self.vm.proc.wait()
        self.assertEqual(self.vm.proc.stdout.read().strip(), "hello-stdout")
        self.assertEqual(self.vm.proc.stderr.read().strip(), "hello-stderr")

    def test_log_fd_merges_stdout_and_stderr(self):
        """passing log_fd routes both real streams into the same real file, and proc.stdout/proc.stderr become None (not PIPE)."""
        self.vm = VirtualMachine(qemu_bin="qemu-system-x86_64", arch="x86_64")
        self.vm.build_command = lambda: _mock_qemu_exec(
            "import sys; print('out-line'); print('err-line', file=sys.stderr)"
        )
        with tempfile.TemporaryFile(mode="w+") as log_fd:
            self.vm.spawn(log_fd=log_fd)
            self.vm.proc.wait()
            self.assertIsNone(self.vm.proc.stdout)
            self.assertIsNone(self.vm.proc.stderr)
            log_fd.seek(0)
            combined = log_fd.read()
            self.assertIn("out-line", combined)
            self.assertIn("err-line", combined)

    def test_default_stdin_is_devnull_and_does_not_block(self):
        """a child that tries to read stdin under the default DEVNULL must see immediate EOF rather than hanging."""
        self.vm = VirtualMachine(qemu_bin="qemu-system-x86_64", arch="x86_64")
        self.vm.build_command = lambda: _mock_qemu_exec(
            "import sys; data = sys.stdin.read(); print(repr(data))"
        )
        self.vm.spawn()
        out, _ = self.vm.proc.communicate(timeout=5)
        self.assertEqual(out.strip(), "''")

    def test_custom_stdin_is_readable_by_child(self):
        """an explicit stdin_dest is honored"""
        self.vm = VirtualMachine(qemu_bin="qemu-system-x86_64", arch="x86_64")
        self.vm.build_command = lambda: _mock_qemu_exec(
            "import sys; print(sys.stdin.read().strip())"
        )
        self.vm.spawn(stdin_dest=subprocess.PIPE)
        out, _ = self.vm.proc.communicate(input="ping-from-test", timeout=5)
        self.assertEqual(out.strip(), "ping-from-test")


class TestVerifyHealth(TestSetup):
    def test_returns_false_when_never_spawned(self):
        """verify_health before spawn() must not raise."""
        self.vm = VirtualMachine(qemu_bin="qemu-system-x86_64", arch="x86_64")
        self.assertFalse(self.vm.verify_health())

    def test_returns_true_for_still_running_process(self):
        """a process still alive after the grace delay passes."""
        self.vm = VirtualMachine(qemu_bin="qemu-system-x86_64", arch="x86_64")
        self.vm.build_command = lambda: _mock_qemu_exec("import time; time.sleep(5)")
        self.vm.spawn()
        self.assertTrue(self.vm.verify_health(delay=0.2))

    def test_raises_with_piped_stderr_on_crash(self):
        """an immediate crash with piped stderr surfaces the real stderr text and exit code in the raised error."""
        self.vm = VirtualMachine(qemu_bin="qemu-system-x86_64", arch="x86_64")
        self.vm.build_command = lambda: _mock_qemu_exec(
            "import sys; sys.stderr.write('qemu: invalid option'); sys.exit(3)"
        )
        self.vm.spawn()
        with self.assertRaises(VirtualEngineError) as ctx:
            self.vm.verify_health(delay=0.2)
        self.assertIn("qemu: invalid option", str(ctx.exception))
        self.assertIn("Exit: 3", str(ctx.exception))

    def test_raises_with_log_fd_stderr_on_crash(self):
        """when spawn() used log_fd instead of PIPE, proc.stderr is None -
        verify_health must fall back to reading the log file"""
        self.vm = VirtualMachine(qemu_bin="qemu-system-x86_64", arch="x86_64")
        self.vm.build_command = lambda: _mock_qemu_exec(
            "import sys; sys.stderr.write('bad option: -m'); sys.exit(1)"
        )
        with tempfile.TemporaryFile(mode="w+") as log_fd:
            self.vm.spawn(log_fd=log_fd)
            with self.assertRaises(VirtualEngineError) as ctx:
                self.vm.verify_health(delay=0.2)
            self.assertIn("bad option: -m", str(ctx.exception))


class TestTeardown(TestSetup):
    def test_terminates_process_that_responds_to_sigterm(self):
        """a process exits on SIGTERM well within the timeout, so kill() is never needed."""
        self.vm = VirtualMachine(qemu_bin="qemu-system-x86_64", arch="x86_64")
        self.vm.build_command = lambda: _mock_qemu_exec("import time; time.sleep(30)")
        self.vm.spawn()
        self.vm.teardown(timeout=5)
        self.assertIsNotNone(self.vm.proc.poll())

    def test_kills_process_that_ignores_sigterm(self):
        """a process that ignores SIGTERM must be force-killed once the timeout elapses."""
        self.vm = VirtualMachine(qemu_bin="qemu-system-x86_64", arch="x86_64")
        self.vm.build_command = lambda: _mock_qemu_exec(
            "import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(30)"
        )
        self.vm.spawn()
        self.vm.teardown(timeout=0.3)
        self.assertIsNotNone(self.vm.proc.poll())

    def test_teardown_without_spawn_is_a_noop(self):
        """tearing down a VM that was never spawned must not raise."""
        self.vm = VirtualMachine(qemu_bin="qemu-system-x86_64", arch="x86_64")
        self.vm.teardown()

    def test_context_manager_tears_down_on_exit(self):
        """Verify the context manager terminates a real running process."""
        vm = VirtualMachine(qemu_bin="qemu-system-x86_64", arch="x86_64")
        vm.build_command = lambda: _mock_qemu_exec("import time; time.sleep(30)")
        with vm:
            vm.spawn()
            self.assertIsNone(vm.proc.poll())
        self.assertIsNotNone(vm.proc.poll())
