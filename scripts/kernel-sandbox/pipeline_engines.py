import hashlib
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from libs.cache_metadata import write_cache_metadata
from libs.container_engine import ContainerEngine
from libs.initrd_builder import create_busybox_initrd, create_dracut_initrd
from libs.virtual_engine import VirtualMachine
from libs.image_customizer import install_rpms_to_image
from libs.ssh_utils import connect_ssh_and_wait, wait_for_ssh_ready
from libs.lock import file_lock
from libs.console import print_phase_header, get_logger
from libs.command import get_printable_cmd
from libs.errors import KernelSandboxError

logger = get_logger(__name__)
CONTAINER_PULL_TIMEOUT = 300
CONTAINER_BUILD_TIMEOUT = 7200


class PipelineError(KernelSandboxError):
    pass


class BuildEngine:
    """Handles the containerized or host-level kernel compilation orchestration phase."""
    def execute(self, ctx):
        if ctx.mode == "fast":
            self._execute_fast(ctx)
        else:
            self._execute_rpm(ctx)

    # ------------------------------------------------------------------
    # Fast mode: containerized bzImage build
    # ------------------------------------------------------------------
    def _execute_fast(self, ctx):
        artifacts_dir = ctx.artifacts_dir
        fast_kernel_cache = artifacts_dir / ctx.kernel_image_name
        initrd_cache = artifacts_dir / "initrd_custom.gz"

        config_path = Path(ctx.workspace) / "config" / ctx.arch / ctx.config_flavor
        if not config_path.exists():
            raise PipelineError(
                f"Kernel configuration missing in workspace: {config_path}\n"
                f"Please verify that the branch contains config/{ctx.arch}/{ctx.config_flavor}."
            )

        # guard the whole cache-check -> build -> cache-write sequence for this
        # specific (commit, arch, config)
        lock_path = artifacts_dir.parent / ".kernel-sandbox-build.lock"
        with file_lock(lock_path, description=f"fast-mode build ({ctx.commit_hash[:7]}/{ctx.arch}/{ctx.config_flavor})"):
            if ctx.refresh_cache and artifacts_dir.exists():
                logger.info(f"Cleared stale cache directories for commit/arch: {ctx.commit_hash}/{ctx.arch}/{ctx.config_flavor}/")
                shutil.rmtree(artifacts_dir)

            if not ctx.refresh_cache and fast_kernel_cache.exists():
                logger.info(
                    f"[CACHE HIT] Found cached {ctx.kernel_image_name} and initrd for "
                    f"commit/arch/config_flavor {ctx.commit_hash}/{ctx.arch}/{ctx.config_flavor}. "
                    "Skipping build."
                )
                return

            git_marker = f"-kernel-sandbox-{ctx.commit_hash[:7]}"

            print_phase_header(
                phase_title="Phase: Host Prep and Containerized Make (Fast Mode)",
                details=[
                    f"compiler_CC: {ctx.cc} (Host: {ctx.host_cc})",
                    f"cross_compile_prefix: {ctx.cross_compile or 'N/A'}",
                    f"target_linux_arch: {ctx.linux_arch}",
                    f"container_target_platform: {ctx.host_arch_platform}",
                    f"artifacts_store: {artifacts_dir.resolve()}",
                    f"target_kernel_cache_store: {fast_kernel_cache.resolve()}"
                ]
            )
            runtime = ContainerEngine.get_container_runtime()
            logger.info(f"Container runtime: {runtime}")
            logger.info(f"Container image: {ctx.container_image}")

            seq_cmd = [
                "./scripts/sequence-patch", "-d", f"kernel-sandbox-sp-{ctx.commit_hash[:7]}-{ctx.arch}-{ctx.config_flavor}",
                f"--config={ctx.arch}-{ctx.config_flavor}", "--rapid"]
            logger.info("[BUILD] Running sequence-patch on host, cmd: " + get_printable_cmd(seq_cmd))
            try:
                subprocess.run(seq_cmd, check=True, cwd=ctx.workspace)
            except subprocess.CalledProcessError as e:
                raise PipelineError(f"sequence-patch failed with exit code {e.returncode}")

            # workspace / f"kernel-sandbox-sp-{commit_hash[:7]}-{arch}-{config_flavor}" / "current"
            # can be safely assumed after a sequence-patch
            config_file = (
                ctx.workspace
                / f"kernel-sandbox-sp-{ctx.commit_hash[:7]}-{ctx.arch}-{ctx.config_flavor}"
                / "current" / ".config"
            )
            if not config_file.exists():
                raise PipelineError(
                    f".config not found after sequence-patch at {config_file}."
                    f"Please verify the branch contains config/{ctx.arch}/{ctx.config_flavor}.")

            linux_dir = config_file.parent
            # amend the kernel config to have networking up and 9p passthrough for fast mode
            config_patch_cmds = [
                f"./scripts/config --enable {cfg}" for cfg in ctx.enable_configs
                ] + [f"./scripts/config --disable {cfg}" for cfg in ctx.disable_configs]
            config_patch_str = " && ".join(config_patch_cmds)
            config_patch_str = f"{config_patch_str} && " if config_patch_str else ""
            container_cmd = (
                f"echo \"{git_marker}\" > localversion && "
                f"make clean && "
                f"{config_patch_str}"
                f"yes \"\" | make oldconfig && "
                f"make -j$(nproc --all)"
            )

            with ContainerEngine(
                    runtime=runtime,
                    storage_root=Path(ctx.cache_dir) / "containers" / "storage",
                    image=ctx.container_image,
                    name=f"kernel-sandbox-{ctx.commit_hash[:7]}-{ctx.arch}-{ctx.config_flavor}"
            ) as container_engine:
                container_engine.pull_image(timeout=CONTAINER_PULL_TIMEOUT)

                env_dict = {
                    "ARCH": ctx.linux_arch,
                    "HOSTCC": ctx.host_cc,
                    "CC": ctx.cc,
                    "CROSS_COMPILE": ctx.cross_compile
                }

                # FIXME: native arch container compilation is too slow, hence prefering cross_compilation always
                # will revisit this later.
                container_engine.execute_command(
                    workspace_path_rw=linux_dir,
                    platform=ctx.host_arch_platform,  # FIXME
                    env_dict=env_dict,
                    cmd_str=container_cmd,
                    workspace_mount="/workspace/",
                    tty=True,
                    timeout=CONTAINER_BUILD_TIMEOUT
                )

                if not ctx.use_busybox_initrd:
                    module_install_root = artifacts_dir / "modules"
                    module_install_root.mkdir(parents=True, exist_ok=True)
                    self.install_modules(
                        linux_dir, container_engine, ctx.host_arch_platform, env_dict, ctx.cross_compile,
                        ctx.cc, ctx.host_cc, module_install_root, ctx.linux_arch
                    )

            built_kernel_path = linux_dir / "arch" / ctx.boot_arch / "boot" / ctx.build_image_name
            if built_kernel_path.exists():
                artifacts_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(built_kernel_path, fast_kernel_cache)
                logger.info(f"Successfully archived built kernel image to cache: {fast_kernel_cache}")
            else:
                raise PipelineError(
                    f"Built kernel image missing (checked at - {built_kernel_path} )after successful compile task pass")

    # ------------------------------------------------------------------
    # RPM mode: native host build via osc
    # ------------------------------------------------------------------
    def _execute_rpm(self, ctx):
        artifacts_dir = ctx.artifacts_dir
        rpm_cache_dir = artifacts_dir / "rpms"
        git_marker = f"-kernel-sandbox-{ctx.commit_hash[:7]}"

        # guard for cache directory
        cache_lock_path = artifacts_dir.parent / ".kernel-sandbox-build.lock"
        build_root_key = hashlib.sha256(str(Path(ctx.rpm_build_root).resolve()).encode()).hexdigest()[:12]
        build_root_lock_path = Path(ctx.cache_dir) / f".kernel-sandbox-build-root-{ctx.rpm_arch}-{build_root_key}.lock"

        with file_lock(cache_lock_path, description=f"rpm-mode build ({ctx.commit_hash[:7]}/{ctx.arch}/{ctx.config_flavor})"):
            if ctx.refresh_cache and artifacts_dir.exists():
                logger.info(
                    f"Cleared stale cache directories for commit/arch: {ctx.commit_hash}/{ctx.arch}/{ctx.config_flavor}/"
                )
                shutil.rmtree(artifacts_dir)

            if not ctx.refresh_cache and rpm_cache_dir.exists():
                if list(rpm_cache_dir.glob(f"kernel-{ctx.config_flavor}*g{ctx.commit_hash[:7]}.{ctx.rpm_arch}.rpm")):
                    logger.info(
                        f"[CACHE HIT] Found cached RPMs for commit/arch/config_flavor: "
                        f"{ctx.commit_hash}/{ctx.arch}/{ctx.config_flavor}. Skipping build."
                    )
                    return

            with file_lock(build_root_lock_path, description=f"osc build root {ctx.rpm_build_root} ({ctx.rpm_arch})"):
                self._run_osc_build(ctx, git_marker)

            # copy RPMs from the system build root
            build_root_system = (
                Path(ctx.rpm_build_root) / "home" / "abuild" / "rpmbuild" / "RPMS" / ctx.rpm_arch
            )
            logger.info(f"Harvesting RPMs from {build_root_system}...")
            rpm_cache_dir.mkdir(parents=True, exist_ok=True)

            rpms_found = list(build_root_system.glob(f"kernel-{ctx.config_flavor}*g{ctx.commit_hash[:7]}.{ctx.rpm_arch}.rpm"))
            if not rpms_found:
                raise PipelineError(
                    f"No RPMs found in {build_root_system} after successful osc build"
                )

            for rpm in rpms_found:
                shutil.copy2(rpm, rpm_cache_dir)

            logger.info(f"Successfully copied and cached {len(rpms_found)} RPMs into unified {rpm_cache_dir} store")

    def _run_osc_build(self, ctx, git_marker):
        def is_ibs_reachable():
            try:
                with urllib.request.urlopen(ctx.ibs_api_url, timeout=3) as resp:
                    return resp.status == 200
            except urllib.error.HTTPError as e:
                return e.code == 401  # reachable, but requires auth
            except (urllib.error.URLError, TimeoutError, OSError):
                return False

        use_ibs = is_ibs_reachable() and bool(ctx.ibs_project)

        api_url = ctx.ibs_api_url if use_ibs else ctx.obs_api_url
        target_project = ctx.ibs_project if use_ibs else ctx.obs_project
        if not target_project:
            raise PipelineError(
                f"Target project (IBS|OBS) not specified for {'IBS' if use_ibs else 'OBS'} (api_url: {api_url}) in rpm/config.sh")

        print_phase_header(
            phase_title="Phase: Native Host RPM Build",
            details=[
                f"Target spec: kernel-{ctx.config_flavor}.spec",
                f"Target OBS architecture: {ctx.rpm_arch}",
                f"Local version git-marker: {git_marker}",
                f"System build_root: {ctx.rpm_build_root}",
                f"Unified rpm cache store: {(ctx.artifacts_dir / 'rpms').resolve()}"
            ]
        )

        tar_up_cmd = ["./scripts/tar-up", "--git", "-d", "kernel-source"]
        logger.info("[BUILD] Running tar-up on host, cmd: " + get_printable_cmd(tar_up_cmd))
        try:
            subprocess.run(tar_up_cmd, check=True, cwd=ctx.workspace)
            # FIXME: it is nice to use ./scripts/osc_wrapper, but it is not working for all arches,
            # hence using osc directly for now.
            # ./scripts/osc_wrapper hardcodes standard <spec>
            # in my testing with `osc` for other arches, even with --target=<arch>,
            # i had to supply standard <arch> spec to get the build to work, hence using osc directly it here
            # will discuss with the team to see if we can get osc_wrapper to work for all arches
            # osc_cmd = [
            #     "./scripts/osc_wrapper", "build", "--clean",
            #     f"--target={rpm_arch}",
            #     "--define=is_kotd 1",  # to get kernel-flavor-RELEASE-ARCH.rpm naming convention
            # ]
            osc_cmd = [
                "osc",
                "-A", api_url,
                "build",
                "--no-service",
                "--local-package",
                f"--alternative-project={target_project}",
                f"--root={ctx.rpm_build_root}",
                "--clean",
                f"--target={ctx.rpm_arch}",
                "--define=is_kotd 1",  # to get kernel-flavor-RELEASE-ARCH.rpm naming convention
                "--debuginfo",
                "--no-checks",
                "--extra-pkgs=-brp-check-suse",
                "--extra-pkgs=-post-build-checks"
            ]
            osc_cmd.extend([
                "standard",
                ctx.rpm_arch,  # FIXME: verify if binfmt is needed for other arches on the dev env.
                f"kernel-source/kernel-{ctx.config_flavor}.spec"
            ])
            logger.info(f"[BUILD] Executing osc_wrapper/osc build on host for {ctx.rpm_arch}, cmd: " + get_printable_cmd(osc_cmd))
            subprocess.run(osc_cmd, check=True, cwd=ctx.workspace)
        except subprocess.CalledProcessError as e:
            raise PipelineError(f"Host RPM build failed with exit code {e.returncode}")

    def install_modules(
            self, linux_dir, container_engine, host_arch_platform, env_dict, cross_compile, cc, host_cc, module_install_root, linux_arch):
        """compile kernel modules inside the container"""
        logger.info("[BUILD] Installing kernel modules inside the container environment...")
        make_args_str = f"ARCH={linux_arch} CROSS_COMPILE={cross_compile} CC={cc} HOSTCC={host_cc}"
        build_steps = [f"make {make_args_str} -j$(nproc --all) modules_install INSTALL_MOD_PATH=/module_root"]
        container_compile_sequence = " && ".join(build_steps)

        container_engine.execute_command(
            workspace_path_rw=linux_dir,
            platform=host_arch_platform,
            env_dict=env_dict,
            cmd_str=container_compile_sequence,
            workspace_mount="/workspace/",
            extra_volumes={str(module_install_root): "/module_root"},
            timeout=CONTAINER_BUILD_TIMEOUT
        )
        logger.info(f"[BUILD] Modules installed and exported to: {module_install_root}")


class ImagePreparer:
    """Prepares target backing structures (Busybox initrd images or custom QCOW2 volumes)."""
    def execute(self, ctx):
        artifacts_dir = ctx.artifacts_dir

        # write to cache unconditionally
        write_cache_metadata(
            artifacts_dir, mode=ctx.mode, arch=ctx.arch, config_flavor=ctx.config_flavor,
            commit_hash=ctx.commit_hash,
            kernel_image_name=getattr(ctx, "kernel_image_name", None),
            rpm_arch=getattr(ctx, "rpm_arch", None),
        )

        if ctx.mode == "rpm":
            rpm_cache_dir = artifacts_dir / "rpms"
            logger.info(f"Preparing {ctx.cow_image} with cache RPMs")
            install_rpms_to_image(ctx.cow_image, ctx.config_flavor, ctx.commit_hash, ctx.rpm_arch, rpm_cache_dir)
            return

        initrd_cache = artifacts_dir / "initrd_custom.gz"

        # create|fetch-from-cache busybox initrd
        if initrd_cache.exists() and not ctx.refresh_cache:
            logger.info(f"[CACHE HIT] cache contains active initrd: {initrd_cache}")
            return

        logger.info(f"Compiling fresh initrd directly to cache target: {initrd_cache}")

        if ctx.use_busybox_initrd:
            logger.info(f"Compiling fresh busybox initrd directly to cache target: {initrd_cache}")
            create_busybox_initrd(
                container_image=ctx.container_image,
                container_platform_host=ctx.host_arch_platform,
                container_platform_target=ctx.target_arch_platform,
                cross_compile=ctx.cross_compile,
                cache_dir=Path(ctx.cache_dir),
                workspace=Path(ctx.workspace),
                output_path=initrd_cache
            )
        else:
            # Dracut initrd build mechanism
            logger.info(f"Compiling fresh dracut initrd directly to cache target: {initrd_cache}")
            module_install_root = artifacts_dir / "modules"
            if not module_install_root.exists():
                raise PipelineError(
                    f"Kernel modules not found at {module_install_root}. "
                    "You must complete the build phase before running the image phase."
                )
            kver_file = (
                ctx.workspace
                / f"kernel-sandbox-sp-{ctx.commit_hash[:7]}-{ctx.arch}-{ctx.config_flavor}"
                / "current"
                / "include"
                / "config"
                / "kernel.release")
            if kver_file.exists():
                kver = kver_file.read_text().strip()
            else:
                raise PipelineError(
                    f"Cannot determine exact kernel version for Dracut: {kver_file} does not exist. "
                    "The kernel source tree must be fully configured and built before this step."
                )

            create_dracut_initrd(
                container_image=ctx.container_image,
                container_platform=ctx.target_arch_platform,
                cache_dir=Path(ctx.cache_dir),
                workspace=Path(ctx.workspace),
                kernel_version=kver,
                module_install_root=module_install_root,
                output_path=initrd_cache,
            )


class BootEngine:
    """Boot with the kernel built to a VM environment"""
    def execute(self, ctx):
        # spawn QEMU
        network_maps = [("user,id=net0,hostfwd=tcp::2222-:22", "virtio-net-pci,netdev=net0")]
        enable_kvm = ctx.arch == ctx.host_arch

        kernel_path = None
        initrd_path = None
        fsdevs = []
        append_str = None
        append_extra = None
        disk_path = None
        artifacts_dir = ctx.artifacts_dir

        if ctx.mode == "fast":
            append_extra = "rdinit=/custom_init"
            kernel_path = artifacts_dir / ctx.kernel_image_name
            initrd_path = artifacts_dir / "initrd_custom.gz"

            if not kernel_path.exists():
                raise PipelineError(f"Built kernel image not found at '{kernel_path}'")

            if not initrd_path.exists():
                raise PipelineError(f"Initrd not found at '{initrd_path}'")

            # Add 9p filesystem passthrough for workspace
            fsdevs.append(
                (f"local,id=hostfs,path={ctx.workspace},security_model=none", "virtio-9p-pci,fsdev=hostfs,mount_tag=host_mount")
            )
        else:
            disk_path = ctx.cow_image

        with VirtualMachine(
            qemu_bin=ctx.qemu_bin,
            arch=ctx.arch,
            ram="4096" if ctx.use_busybox_initrd else "8192",
            smp="4" if ctx.use_busybox_initrd else "8",
            disk_path=disk_path,
            network_maps=network_maps,
            extra_qemu_args=ctx.extra_qemu,
            enable_kvm=enable_kvm,
            kernel=kernel_path,
            initrd=initrd_path,
            append=append_str,
            append_extra=append_extra,
            fsdevs=fsdevs,
            machine_cpu_console_profile=ctx.qemu_profile
        ) as vm:

            # SSH auto-connect strategy: always on in rpm mode, opt-in via `--ssh` in fast mode.
            auto_ssh = ctx.ssh_enabled or (ctx.mode == "rpm")

            qemu_cmd = vm.build_command()
            logger.info(f"QEMU command: {get_printable_cmd(qemu_cmd)}")

            if auto_ssh:
                logger.info("Launching QEMU in background...")

                # Create a temporary file to capture QEMU stderr
                qemu_log = tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".log")
                qemu_log_path = Path(qemu_log.name)
                qemu_log.close()

                boot_success = False
                try:
                    with qemu_log_path.open("w") as log_file:
                        vm.spawn(log_fd=log_file)

                    vm.verify_health()
                    logger.info(f"QEMU started (PID: {vm.proc.pid})")

                    # Wait for SSH to become available
                    if wait_for_ssh_ready(port=2222, timeout=180):
                        # Connect via SSH
                        boot_success = connect_ssh_and_wait(port=2222)
                    else:
                        raise PipelineError("SSH did not become available - VM may have failed to boot")

                finally:
                    if not boot_success and qemu_log_path.exists():
                        try:
                            err_out = qemu_log_path.read_text().strip()
                            if err_out:
                                logger.warning(f"VM crashed or SSH failed. QEMU Telemetry:\n{err_out}")
                        except OSError as e:
                            logger.warning(f"Could not read QEMU crash log at {qemu_log_path}: {e}")
                    if qemu_log_path.exists():
                        qemu_log_path.unlink()

            else:
                # Reached only in fast mode without --ssh - rpm mode is always covered by the auto_ssh branch above.
                print_phase_header(
                    "Sandbox active!\n"
                    f"Host Worktree: {Path(ctx.workspace).resolve()}\n"
                    "Mounted in guest at: /mnt/workspace"
                )

                try:
                    vm.spawn(stdin_dest=sys.stdin, stdout_dest=sys.stdout, stderr_dest=sys.stderr)
                    vm.verify_health()
                    vm.proc.wait()
                except KeyboardInterrupt:
                    logger.info("QEMU execution interrupted by user")
