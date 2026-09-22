import contextlib
import os
import sys
import tempfile
import unittest
from pathlib import Path

import libs.container_engine as container_engine_module
from libs.container_engine import ContainerEngine, ContainerRuntimeError


def _mock_executable(directory, name):
    path = Path(directory) / name
    path.write_text("#!/bin/sh\necho mock_binary\n")
    path.chmod(0o755)
    return path


@contextlib.contextmanager
def _redirect_real_fd(fd, target_file):
    """Redirects a real OS file descriptor (not sys.stdout/sys.stderr) to
    target_file for the duration of the block"""
    saved_fd = os.dup(fd)
    try:
        os.dup2(target_file.fileno(), fd)
        yield
    finally:
        os.dup2(saved_fd, fd)
        os.close(saved_fd)


class TestGetContainerRuntime(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmpdir.cleanup()

    def _create_executables(self, *names):
        for name in names:
            _mock_executable(self.tmpdir.name, name)
        return self.tmpdir.name

    def test_prefers_podman_when_both_available(self):
        custom_path = self._create_executables("podman", "docker")
        self.assertEqual(ContainerEngine.get_container_runtime(path=custom_path), "podman")

    def test_uses_podman_when_only_podman_available(self):
        custom_path = self._create_executables("podman")
        self.assertEqual(ContainerEngine.get_container_runtime(path=custom_path), "podman")

    def test_raises_when_only_docker_available(self):
        """docker-only must hard-refuse, not silently fall back."""
        custom_path = self._create_executables("docker")
        with self.assertRaises(ContainerRuntimeError) as ctx:
            ContainerEngine.get_container_runtime(path=custom_path)
        self.assertIn("Docker is available but podman is preferred", str(ctx.exception))

    def test_raises_when_neither_available(self):
        """no runtime at all."""
        with self.assertRaises(ContainerRuntimeError) as ctx:
            ContainerEngine.get_container_runtime(path=self.tmpdir.name)
        self.assertIn("Neither podman nor docker is available", str(ctx.exception))


class TestBuildCommand(unittest.TestCase):
    def setUp(self):
        self.storage_root = "/tmp/podman-root"
        self.image = "localhost/kernel-build:latest"
        self.engine = ContainerEngine(runtime="podman", storage_root=self.storage_root, image=self.image)

    def test_podman_basic(self):
        """Verify podman command generation with required parameters."""
        cmd = self.engine.build_command(
            workspace_path_rw="/home/user/src",
            platform="linux/amd64",
            env_dict={"ARCH": "x86_64", "CROSS_COMPILE": "x86_64-linux-gnu-"},
            cmd_str="make bzImage"
        )

        self.assertEqual(cmd[0], "podman")
        self.assertEqual(cmd[cmd.index("--root") + 1], self.storage_root)
        self.assertIn("run", cmd)
        self.assertIn("--rm", cmd)

        # rootless flags
        self.assertIn("--userns=keep-id", cmd)
        self.assertIn("label=disable", cmd[cmd.index("--security-opt") + 1])

        # env and execution command mapping
        self.assertIn("-e", cmd)
        self.assertIn("ARCH=x86_64", cmd)
        self.assertIn("CROSS_COMPILE=x86_64-linux-gnu-", cmd)
        self.assertEqual(cmd[-4:], [self.image, "bash", "-c", "make bzImage"])

    def test_podman_optional_workspace_and_defaults(self):
        """Verify defaults apply when optional args are omitted."""
        cmd = self.engine.build_command()
        self.assertEqual(cmd[cmd.index("--platform") + 1], "linux/x86_64")
        self.assertEqual(cmd[-4:], [self.image, "bash", "-c", "bash"])
        self.assertNotIn("-w", cmd)

    def test_docker_omits_podman_specific_flags(self):
        """Verify docker's command omits podman-only flags."""
        docker_engine = ContainerEngine(runtime="docker", storage_root=self.storage_root, image=self.image)
        cmd = docker_engine.build_command(
            workspace_path_rw="/tmp/space", platform="linux/arm64", env_dict={}, cmd_str="exit 0")
        self.assertNotIn("--root", cmd)
        self.assertNotIn("--userns=keep-id", cmd)
        self.assertNotIn("--security-opt", cmd)

    def test_as_root_skips_userns_keep_id(self):
        """as_root=True must not add --userns=keep-id."""
        cmd = self.engine.build_command(as_root=True)
        self.assertNotIn("--userns=keep-id", cmd)

    def test_resource_limits_and_extra_volumes(self):
        """Validate resource constraints and secondary volume mount processing."""
        extra_vols = {
            "/some/read_only": "/some/read_only:ro",
            "/some/read_write": "/some/read_write:rw",
            "/some/no_flags": "/some/no_flags",
        }
        cmd = self.engine.build_command(
            workspace_path_rw="/tmp/space", platform="linux/amd64", env_dict={},
            extra_volumes=extra_vols, cmd_str="make", memory_limit="8g", cpu_limit="4")

        self.assertEqual(cmd[cmd.index("--memory") + 1], "8g")
        self.assertEqual(cmd[cmd.index("--cpus") + 1], "4")

        for host_p, guest_p in extra_vols.items():
            resolved_host_p = str(Path(host_p).resolve())
            expected_mount = f"{resolved_host_p}:{guest_p}"
            indices = [i for i, x in enumerate(cmd) if x == "-v"]
            mount_found = any(cmd[idx + 1] == expected_mount for idx in indices)
            self.assertTrue(mount_found, f"Volume mapping '{expected_mount}' missing.")

    def test_interactive_sets_it_flag(self):
        cmd = self.engine.build_command(cmd_str="bash", interactive=True)
        self.assertIn("-it", cmd)

    def test_tty_sets_t_only_not_it(self):
        """tty=True is for streaming a non-interactive command's output live, it should not also open stdin (-i)"""
        cmd = self.engine.build_command(cmd_str="bash", tty=True)
        self.assertIn("-t", cmd)
        self.assertNotIn("-it", cmd)
        self.assertNotIn("-i", cmd)

    def test_interactive_sets_it_only_not_t(self):
        cmd = self.engine.build_command(cmd_str="bash", interactive=True, tty=True)
        self.assertIn("-it", cmd)
        self.assertNotIn("-t", cmd)

    def test_neither_interactive_nor_tty_omits_both_flags(self):
        cmd = self.engine.build_command(cmd_str="bash")
        self.assertNotIn("-it", cmd)
        self.assertNotIn("-t", cmd)

    def test_empty_resource_limits_are_omitted(self):
        """false limits must not emit empty flags."""
        cmd = self.engine.build_command(memory_limit=None, cpu_limit="")
        self.assertNotIn("--memory", cmd)
        self.assertNotIn("--cpus", cmd)

    def test_name_omitted_when_not_set(self):
        self.assertNotIn("--name", self.engine.build_command())

    def test_name_included_when_set(self):
        named_engine = ContainerEngine(
            runtime="podman", storage_root=self.storage_root, image=self.image, name="kernel-sandbox-abc1234-x86_64-default")
        cmd = named_engine.build_command()
        self.assertEqual(cmd[cmd.index("--name") + 1], "kernel-sandbox-abc1234-x86_64-default")


class TestBuildPullCommand(unittest.TestCase):
    def test_podman_includes_root_as_two_tokens(self):
        engine = ContainerEngine(runtime="podman", storage_root="/tmp/podman-root", image="my-image")
        cmd = engine.build_pull_command()
        self.assertEqual(cmd, ["podman", "--root", "/tmp/podman-root", "pull", "my-image"])

    def test_docker_omits_root(self):
        engine = ContainerEngine(runtime="docker", storage_root="/tmp/podman-root", image="my-image")
        cmd = engine.build_pull_command()
        self.assertEqual(cmd, ["docker", "pull", "my-image"])


class TestBuildRemoveCommand(unittest.TestCase):
    def test_podman_includes_root(self):
        engine = ContainerEngine(runtime="podman", storage_root="/tmp/podman-root", image="unused", name="my-container")
        cmd = engine.build_remove_command()
        self.assertEqual(cmd, ["podman", "--root", "/tmp/podman-root", "rm", "-f", "my-container"])

    def test_docker_omits_root(self):
        engine = ContainerEngine(runtime="docker", storage_root="/tmp/podman-root", image="unused", name="my-container")
        cmd = engine.build_remove_command()
        self.assertEqual(cmd, ["docker", "rm", "-f", "my-container"])


class TestRemoveContainer(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_noop_when_name_not_set(self):
        """No name means execute_command() never created a named container -
        nothing to clean up, and no subprocess should even be spawned."""
        calls = []
        original_run = container_engine_module.subprocess.run
        container_engine_module.subprocess.run = lambda *a, **k: calls.append(a)
        try:
            engine = ContainerEngine(runtime="podman", storage_root="/tmp", image="unused")
            engine.remove_container()
        finally:
            container_engine_module.subprocess.run = original_run
        self.assertEqual(calls, [])

    def test_behaviour_nonzero_exit_when_container_already_gone(self):
        """rm -f on an already-cleaned-up container"""
        runtime = _mock_executable(self.tmp_dir.name, "mock-runtime")
        runtime.write_text("#!/bin/sh\necho 'Error: no such container' >&2\nexit 1\n")
        engine = ContainerEngine(runtime=str(runtime), storage_root="/tmp", image="unused", name="ghost-container")
        engine.remove_container()  # must not raise

    def test_actually_invokes_the_runtime_with_expected_args(self):
        call_log = Path(self.tmp_dir.name) / "calls.log"
        runtime = _mock_executable(self.tmp_dir.name, "mock-runtime")
        runtime.write_text(f"#!/bin/sh\necho \"$@\" >> {call_log}\nexit 0\n")
        engine = ContainerEngine(
            runtime=str(runtime), storage_root="/tmp/storage", image="unused", name="kernel-sandbox-abc1234-x86_64-default")
        engine.remove_container()
        self.assertTrue(call_log.exists())
        self.assertEqual("rm -f kernel-sandbox-abc1234-x86_64-default", call_log.read_text().strip())

    def test_missing_runtime_binary_is_swallowed_with_warning(self):
        """missing runtime binary must not raise out of remove_container()"""
        engine = ContainerEngine(
            runtime="/does-not-exist/podman", storage_root="/tmp", image="unused", name="ghost")
        with self.assertLogs("kernel_sandbox", level="WARNING") as log_ctx:
            engine.remove_container()  # must not raise
        self.assertTrue(any("Failed to force-remove container 'ghost'" in msg for msg in log_ctx.output))
        self.assertTrue(any("No such file or directory: '/does-not-exist/podman'" in msg for msg in log_ctx.output))

    def test_remove_container_timeout_with_warning(self):
        """A hung or long running runtime/storage backend must not hang cleanup forever -
        remove_container() must bound to its own timeout"""
        runtime = _mock_executable(self.tmp_dir.name, "mock-runtime")
        runtime.write_text("#!/bin/sh\nsleep 5\n")
        engine = ContainerEngine(runtime=str(runtime), storage_root="/tmp", image="unused", name="hung-container")
        with self.assertLogs("kernel_sandbox", level="WARNING") as log_ctx:
            engine.remove_container(timeout=0.3)  # must return promptly, not raise/hang
        self.assertTrue(
            any(
                "Failed to force-remove container 'hung-container': "
                "Containerized execution timed out after 0.3s:" in msg
                for msg in log_ctx.output
            )
        )


class TestRun(unittest.TestCase):
    """Test ContainerEngine._run()'s subprocess execution and error-wrapping behavior"""
    def setUp(self):
        self.engine = ContainerEngine(runtime="unused", storage_root="/tmp", image="unused")

    def test_returns_completed_process_on_success(self):
        res = self.engine._run([sys.executable, "-c", "print('ok')"])
        self.assertEqual(res.returncode, 0)
        self.assertEqual(res.stdout.strip(), "ok")

    def test_raises_container_runtime_error_on_failure(self):
        with self.assertRaises(ContainerRuntimeError) as ctx:
            self.engine._run([sys.executable, "-c", "import sys; sys.stderr.write('fail-here'); sys.exit(2)"])
        self.assertIn("Exit Code 2", str(ctx.exception))
        self.assertIn("fail-here", str(ctx.exception))

    def test_failure_message_includes_the_actual_command(self):
        """the exception must show what was run"""
        with self.assertRaises(ContainerRuntimeError) as ctx:
            self.engine._run([sys.executable, "-c", "import sys; sys.exit(9)"])
        self.assertIn("Containerized execution failed (Exit Code 9): Unknown container error", str(ctx.exception))
        self.assertIn(sys.executable, str(ctx.exception))

    def test_check_false_does_not_raise_on_nonzero_exit(self):
        res = self.engine._run([sys.executable, "-c", "import sys; sys.exit(3)"], check=False)
        self.assertEqual(res.returncode, 3)

    def test_default_stdin_is_closed_not_inherited(self):
        """neither interactive nor tty -> captured (PIPE/PIPE, closed stdin)"""
        res = self.engine._run([sys.executable, "-c", "import sys; print(repr(sys.stdin.read()))"])
        self.assertEqual(res.stdout.strip(), "''")

    def test_tty_streams_output_and_inherits_real_stdin(self):
        """tty=True -> streamed output, and stdin inherited"""
        with tempfile.TemporaryFile(mode="w+") as mock_stdin:
            mock_stdin.write("hello-from-host\n")
            mock_stdin.seek(0)
            with _redirect_real_fd(0, mock_stdin):
                with tempfile.TemporaryFile(mode="w+") as mock_stdout:
                    with _redirect_real_fd(1, mock_stdout):
                        res = self.engine._run(
                            [sys.executable, "-c", "import sys; print(sys.stdin.read().strip()); print('done')"],
                            tty=True)

                    self.assertIsNone(res.stdout)
                    mock_stdout.seek(0)
                    output = mock_stdout.read()
                    self.assertIn("hello-from-host", output)
                    self.assertIn("done", output)

    def test_interactive_stdin_is_actually_readable_by_child(self):
        """interactive=True -> real stdin + streamed output"""
        with tempfile.TemporaryFile(mode="w+") as mock_stdin:
            mock_stdin.write("hello-from-host\n")
            mock_stdin.seek(0)
            with _redirect_real_fd(0, mock_stdin):
                with tempfile.TemporaryFile(mode="w+") as mock_stdout:
                    with _redirect_real_fd(1, mock_stdout):
                        self.engine._run(
                            [sys.executable, "-c", "import sys; print(sys.stdin.read().strip())"], interactive=True)
                    mock_stdout.seek(0)
                    self.assertEqual(mock_stdout.read().strip(), "hello-from-host")

    def test_interactive_inherits_real_streams(self):
        """interactive=True passes stdout/stderr=None, so the child inherits the real fd 1/2 directly"""
        with tempfile.TemporaryFile(mode="w+") as mock_stdout:
            with _redirect_real_fd(1, mock_stdout):
                res = self.engine._run([sys.executable, "-c", "print('shown live')"], interactive=True)

            self.assertIsNone(res.stdout)
            self.assertIsNone(res.stderr)
            self.assertEqual(res.returncode, 0)
            mock_stdout.seek(0)
            self.assertIn("shown live", mock_stdout.read())

    def test_interactive_failure_falls_back_to_generic_message(self):
        with tempfile.TemporaryFile(mode="w+") as mock_stderr:
            with _redirect_real_fd(2, mock_stderr):
                with self.assertRaises(ContainerRuntimeError) as ctx:
                    self.engine._run(
                        [sys.executable, "-c", "import sys; sys.stderr.write('live error'); sys.exit(1)"],
                        interactive=True)

            self.assertIn("Unknown container error", str(ctx.exception))
            mock_stderr.seek(0)
            self.assertIn("live error", mock_stderr.read())


class TestExecuteCommandAndPullImage(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmpdir.cleanup()

    def _mock_runtime(self, script_body):
        path = Path(self.tmpdir.name) / "mock-runtime"
        path.write_text(f"#!/bin/sh\n{script_body}\n")
        path.chmod(0o755)
        return str(path)

    def test_execute_command_success(self):
        engine = ContainerEngine(
            runtime=self._mock_runtime("echo container-output; exit 0"), storage_root="/tmp", image="mock-image")
        res = engine.execute_command(cmd_str="anything")
        self.assertEqual(res.returncode, 0)
        self.assertIn("container-output", res.stdout)

    def test_execute_command_failure_raises(self):
        engine = ContainerEngine(
            runtime=self._mock_runtime("echo fail-here >&2; exit 5"), storage_root="/tmp", image="mock-image")
        with self.assertRaises(ContainerRuntimeError) as ctx:
            engine.execute_command(cmd_str="anything")
        self.assertIn("fail-here", str(ctx.exception))
        self.assertIn("Exit Code 5", str(ctx.exception))

    def test_execute_command_missing_runtime_binary_raises_wrapped_error(self):
        engine = ContainerEngine(
            runtime="/does-not-exist/podman", storage_root="/tmp", image="mock-image")
        with self.assertRaises(ContainerRuntimeError) as ctx:
            engine.execute_command(cmd_str="anything")
        self.assertIn("Failed to launch container runtime", str(ctx.exception))
        self.assertIn("No such file or directory: '/does-not-exist/podman'", str(ctx.exception))

    def test_execute_command_non_executable_runtime_raises_wrapped_error(self):
        non_exec = Path(self.tmpdir.name) / "podman"
        non_exec.write_text("#!/bin/sh\necho test\n")
        non_exec.chmod(0o644)  # EACCES, not ENOENT
        engine = ContainerEngine(runtime=str(non_exec), storage_root="/tmp", image="mock-image")
        with self.assertRaises(ContainerRuntimeError) as ctx:
            engine.execute_command(cmd_str="anything")
        self.assertIn("Failed to launch container runtime", str(ctx.exception))
        self.assertIn("Permission denied:", str(ctx.exception))

    def test_execute_command_times_out_and_force_removes_container(self):
        call_log = Path(self.tmpdir.name) / "calls.log"
        runtime = self._mock_runtime(
            f'echo "$@" >> {call_log}\n'
            f'if [ "$1" = "rm" ]; then exit 0; fi\n'
            f'sleep 5'
        )
        engine = ContainerEngine(runtime=runtime, storage_root="/tmp", image="mock-image", name="hung-container")
        with self.assertRaises(ContainerRuntimeError) as ctx:
            engine.execute_command(cmd_str="anything", timeout=0.3)
        self.assertIn("Containerized execution timed out after 0.3s:", str(ctx.exception))

        logged_calls = call_log.read_text().strip().splitlines()
        self.assertTrue(any(line.startswith("rm -f hung-container") for line in logged_calls))

    def test_execute_command_handles_non_utf8_output_without_crashing(self):
        engine = ContainerEngine(
            runtime=self._mock_runtime("printf '\\377\\376 bad-bytes'; exit 0"),
            storage_root="/tmp", image="mock-image")
        res = engine.execute_command(cmd_str="anything")
        self.assertEqual(res.returncode, 0)
        self.assertEqual(res.stdout, "�� bad-bytes")

    def test_pull_image_success_does_not_raise(self):
        engine = ContainerEngine(
            runtime=self._mock_runtime("exit 0"), storage_root="/tmp", image="mock-image")
        engine.pull_image()

    def test_pull_image_failure_raises(self):
        """pull_image() must wrap failures as ContainerRuntimeError"""
        engine = ContainerEngine(
            runtime=self._mock_runtime("exit 7"), storage_root="/tmp", image="mock-image")
        with self.assertRaises(ContainerRuntimeError):
            engine.pull_image()

    def test_pull_image_respects_timeout(self):
        engine = ContainerEngine(runtime=self._mock_runtime("sleep 5"), storage_root="/tmp", image="mock-image")
        with self.assertRaises(ContainerRuntimeError) as ctx:
            engine.pull_image(timeout=0.3)
        self.assertIn("Containerized execution timed out after 0.3s:", str(ctx.exception))


class _MockContainerEngine(ContainerEngine):
    """records remove_container() calls"""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.remove_container_calls = 0

    def remove_container(self, timeout=None):
        self.remove_container_calls += 1


class TestContainerEngineEntryExit(unittest.TestCase):
    def setUp(self):
        self.engine = _MockContainerEngine(runtime="unused", storage_root="/tmp", image="unused", name="ctx-test")

    def test_enter_calls_remove_container_and_returns_self(self):
        with self.engine as returned:
            self.assertIs(returned, self.engine)
            self.assertEqual(self.engine.remove_container_calls, 1)

    def test_exit_calls_remove_container_again_on_clean_exit(self):
        with self.engine:
            pass
        self.assertEqual(self.engine.remove_container_calls, 2)  # once on enter, once on exit

    def test_exit_calls_remove_container_and_still_propagates_exception(self):
        with self.assertRaises(ValueError):
            with self.engine:
                raise ValueError("error mid-build")
        self.assertEqual(self.engine.remove_container_calls, 2)
