import shutil
import subprocess
from pathlib import Path
from libs.command import get_printable_cmd
from libs.console import get_logger
from libs.errors import KernelSandboxError

logger = get_logger(__name__)
DEFAULT_CLEANUP_TIMEOUT = 30


class ContainerRuntimeError(KernelSandboxError):
    pass


class ContainerEngine:
    __slots__ = ("runtime", "storage_root", "image", "name")

    def __init__(self, runtime, storage_root, image, name=None):
        self.runtime = runtime
        self.storage_root = Path(storage_root)
        self.image = image
        self.name = name

    def __enter__(self):
        # remove any same-named container a previous, interrupted
        # run may have left running before it could clean up after itself.
        self.remove_container()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # guarantees no container survives this block on any exit path
        # (normal completion, exception, or a signal-triggered SystemExit) -
        # SIGKILL-ing the podman/docker client alone does not reliably stop
        # the container it started, since podman detaches the container's
        # process (via conmon) from its own CLI client process.
        self.remove_container()
        return False

    @staticmethod
    def get_container_runtime(path=None):
        """Detect container runtime - podman preferred"""
        if shutil.which("podman", path=path):
            return "podman"

        if shutil.which("docker", path=path):
            logger.error("Docker found but podman is required - rootless mode is not guaranteed under docker")
            raise ContainerRuntimeError("Docker is available but podman is preferred.")

        logger.error("Neither podman nor docker is available")
        raise ContainerRuntimeError("Neither podman nor docker is available.")

    def build_pull_command(self):
        cmd = [self.runtime]
        # docker CLI does not support --root
        if self.runtime == "podman":
            cmd.extend(["--root", str(self.storage_root)])
        cmd.extend(["pull", self.image])
        return cmd

    def pull_image(self, timeout=None):
        logger.info(f"Pulling latest image: {self.image}")
        self._run(self.build_pull_command(), tty=True, timeout=timeout)

    def build_remove_command(self):
        cmd = [self.runtime]
        if self.runtime == "podman":
            cmd.extend(["--root", str(self.storage_root)])
        cmd.extend(["rm", "-f", self.name])
        return cmd

    def remove_container(self, timeout=DEFAULT_CLEANUP_TIMEOUT):
        """force-stops and removes the named container, if any is running"""
        if not self.name:
            return
        try:
            self._run(self.build_remove_command(), interactive=False, timeout=timeout, check=False)
        except ContainerRuntimeError as e:
            logger.warning(f"Failed to force-remove container '{self.name}': {e}")

    def build_command(
            self, workspace_path_rw=None, platform="linux/x86_64", env_dict=None, cmd_str="bash",
            workspace_mount="/workspace/", interactive=False, tty=False,
            extra_volumes=None, memory_limit=None, cpu_limit=None, pull_policy="missing", as_root=False):
        cmd = [self.runtime]
        # docker CLI does not support --root
        if self.runtime == "podman":
            cmd.extend(["--root", str(self.storage_root)])
        cmd.extend(["run", "--rm", f"--pull={pull_policy}"])
        if self.name:
            cmd.extend(["--name", self.name])

        # interactive: interactive session - keeps the container's
        #     stdin open and connected to (-it). Use this only when
        #     something inside the container actually needs to read input.
        # tty: allocates a pseudo-TTY without opening stdin (-t only).
        #      ignored if interactive=True.
        if interactive:
            cmd.append("-it")
        elif tty:
            cmd.append("-t")

        if self.runtime == "podman":
            if not as_root:
                cmd.extend(["--userns=keep-id"])
            cmd.extend(["--security-opt", "label=disable"])
        if workspace_path_rw:
            cmd.extend([
                "-v", f"{Path(workspace_path_rw).resolve()}:{workspace_mount}:rw",
                "-w", workspace_mount
            ])
        cmd.extend(["--platform", platform])
        for flag, val in (("--memory", memory_limit), ("--cpus", cpu_limit)):
            if val:
                cmd.extend([flag, str(val)])

        if extra_volumes:
            for host_p, guest_p in extra_volumes.items():
                cmd.extend(["-v", f"{Path(host_p).resolve()}:{guest_p}"])

        if env_dict:
            for k, v in env_dict.items():
                cmd.extend(["-e", f"{k}={v}"])

        cmd.extend([self.image, "bash", "-c", cmd_str])
        return cmd

    def execute_command(
            self, workspace_path_rw=None, platform="linux/x86_64", env_dict=None, cmd_str="bash",
            workspace_mount="/workspace/", interactive=False, tty=False,
            extra_volumes=None, memory_limit=None, cpu_limit=None, pull_policy="missing", as_root=False, timeout=None):
        cmd = self.build_command(
            workspace_path_rw=workspace_path_rw, platform=platform, env_dict=env_dict, cmd_str=cmd_str,
            workspace_mount=workspace_mount, interactive=interactive, tty=tty, extra_volumes=extra_volumes,
            memory_limit=memory_limit, cpu_limit=cpu_limit, pull_policy=pull_policy, as_root=as_root)
        logger.info("Running cmd: " + get_printable_cmd(cmd))
        return self._run(cmd, interactive=interactive, tty=tty, timeout=timeout)

    def _run(self, cmd, interactive=False, tty=False, timeout=None, check=True):
        printable = get_printable_cmd(cmd)
        # stdout/stderr=None means "inherit the real fds" (live streaming),
        # for either a genuine interactive session or a tty-only stream.
        # stdin=None for BOTH interactive and tty-only
        # FIXME: Why we use `stdin=None` (inherit) instead of DEVNULL for stream_output (even for non-interactive sessions):
        # Using `podman -t` via `subprocess.run` hangs during cross-arch (ex: ppc64le on aarch64) dracut
        # image builds when `stdin=subprocess.DEVNULL` is assigned.
        # Running the exact same command directly in a terminal works flawlessly.
        # Inheriting the host's real PTY for stdin safely bypasses this hang.
        stream_output = interactive or tty
        try:
            res = subprocess.run(
                cmd,
                stdin=None if stream_output else subprocess.DEVNULL,
                stdout=None if stream_output else subprocess.PIPE,
                stderr=None if stream_output else subprocess.PIPE,
                text=True,
                errors="replace",
                timeout=timeout,
                check=check
            )
        except subprocess.TimeoutExpired as e:
            if check:
                self.remove_container()
            stderr = e.stderr.strip() if e.stderr else ""
            raise ContainerRuntimeError(
                f"Containerized execution timed out after {timeout}s: {printable}"
                + (f"\nPartial stderr: {stderr}" if stderr else "")
            )
        except OSError as e:
            raise ContainerRuntimeError(f"Failed to launch container runtime ({printable}): {e}")

        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.strip() if e.stderr else "Unknown container error"
            raise ContainerRuntimeError(
                f"Containerized execution failed (Exit Code {e.returncode}): {error_msg}\nCommand: {printable}"
            )

        return res
