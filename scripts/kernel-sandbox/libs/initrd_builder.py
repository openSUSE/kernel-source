"""
This initrd builder and its tests may be obsoleted/rewritten in the near future to make way to rapido-linux/rapido generated initrd/boot
"""
import gzip
import shutil
import subprocess
import tarfile
from pathlib import Path
from libs.console import get_logger
from libs.container_engine import ContainerEngine, ContainerRuntimeError
from libs.errors import KernelSandboxError
from libs.lock import file_lock
from libs.storage_manager import HTTPDownloader

logger = get_logger(__name__)


class InitrdBuildError(KernelSandboxError):
    pass


def _load_template(template_path, description):
    """Reads a template asset, raising InitrdBuildError with `description` if missing."""
    template_path = Path(template_path)
    if not template_path.exists():
        raise InitrdBuildError(f"{description} missing at {template_path}")
    return template_path.read_text(encoding="utf-8")


def _render_template(template_text, substitutions):
    """Applies {{KEY}} -> value substitutions to template_text."""
    for key, value in substitutions.items():
        template_text = template_text.replace(f"{{{{{key}}}}}", value)
    return template_text


def compile_busybox(busybox_build_dir, container_engine, platform, cross_compile, build_config_patches=None):
    """compiles busybox for the given branch,arch inside the container runtime."""
    # Build up base configuration modifications dynamically
    config_steps = [
        "make distclean",
        "make defconfig",
        'sed -i "s/# CONFIG_STATIC is not set/CONFIG_STATIC=y/" .config'
    ]

    # Apply standard patches if no custom overrides are supplied
    if build_config_patches is None:
        build_config_patches = {
            "CONFIG_TC": "n",
            "CONFIG_USE_BB_CRYPT_YES": "n"
        }

    for key, val in build_config_patches.items():
        if val == "n":
            config_steps.append(f'sed -i "s/{key}=y/# {key} is not set/" .config')
        elif val == "y":
            config_steps.append(f'sed -i "s/# {key} is not set/{key}=y/" .config')

    # compilation assembly
    compile_cmd = f"make -j$(nproc) CROSS_COMPILE={cross_compile} CC={cross_compile}gcc HOSTCC=gcc"
    config_steps.append(compile_cmd)

    container_compile_sequence = " && ".join(config_steps)

    container_engine.execute_command(
        workspace_path_rw=busybox_build_dir,
        platform=platform,
        env_dict={},
        cmd_str=container_compile_sequence,
        workspace_mount="/build",
        tty=True
    )


def generate_applet_symlinks(container_engine, busybox_build_dir, platform, initrd_dir):
    """Generates the absolute symlinks matching the internal applets registered within the compiled busybox binary."""
    logger.info("Creating busybox symlinks...")
    try:
        applet_result = container_engine.execute_command(
            workspace_path_rw=busybox_build_dir,
            platform=platform,
            env_dict={},
            cmd_str="./busybox --list"
        )
        applets = applet_result.stdout.strip().splitlines()

        for applet in applets:
            applet = applet.strip()
            if not applet:
                continue
            link_path = initrd_dir / "bin" / applet
            if not link_path.exists():
                logger.info(f"symlinking {link_path.name} to 'busybox'")
                link_path.symlink_to("busybox")
    except ContainerRuntimeError as e:
        raise InitrdBuildError(f"Failed to list busybox applets: {e}")


def pack_ramdisk_archive(initrd_dir, initrd_output, cpio_timeout=30, cpio_bin="cpio"):
    """
    Equivalent of
    ```
    find . -print0 | cpio --null -ov --format=newc | gzip -9 > /tmp/initrd_custom.gz
    ```
    FIXME: the whole archive sits in memory before being written to
    initrd_output, rather than streamed straight through gzip - fine for
    the busybox-sized initrds this builds, worth revisiting if that changes.
    this won't be a concern if we transition away from this approach to rapido-generated initrds.
    """
    logger.info("Packing initrd...")
    initrd_output.parent.mkdir(parents=True, exist_ok=True)

    # generate path list: `find . -print0`
    paths = ["."]
    for p in initrd_dir.rglob("*"):
        paths.append(f"./{p.relative_to(initrd_dir)}")

    file_list = "\0".join(paths) + "\0"
    file_list_bytes = file_list.encode("utf-8")

    try:
        result = subprocess.run(
            [cpio_bin, "--null", "-ov", "--format=newc"],
            input=file_list_bytes,
            capture_output=True,
            cwd=initrd_dir,
            timeout=cpio_timeout,
        )
    except subprocess.TimeoutExpired:
        raise InitrdBuildError("cpio process timed out during archive creation")
    except OSError as e:
        raise InitrdBuildError(f"Failed to create initrd archive package: {e}")

    if result.returncode != 0:
        err_msg = result.stderr.decode("utf-8").strip() if result.stderr else "Unknown cpio error"
        raise InitrdBuildError(f"cpio archive creation failed: {err_msg}")

    with gzip.open(initrd_output, "wb", compresslevel=9) as f:
        f.write(result.stdout)

    logger.info(f"Initrd created at {initrd_output}")


def create_busybox_initrd(
        container_image, container_platform_host, container_platform_target, cross_compile, cache_dir, workspace,
        template_path=None, output_path=None, build_config_patches=None, cpio_bin="cpio"):
    """Create a dynamic busybox-based initrd for fast boot mode."""
    logger.info("Creating busybox initrd...")

    initrd_dir = workspace / "tmp" / "initramfs"
    if initrd_dir.exists():
        shutil.rmtree(initrd_dir)

    # initrd directory structure
    for subdir in ["bin", "sbin", "etc", "proc", "sys", "dev", "tmp"]:
        (initrd_dir / subdir).mkdir(parents=True, exist_ok=True)

    busybox_build_dir = cache_dir / "busybox-source"
    busybox_build_dir.mkdir(parents=True, exist_ok=True)
    archive_path = busybox_build_dir / "busybox-snapshot.tar.bz2"

    # busybox_build_dir is shared across and compile_busybox() builds
    # in place inside it - guard the whole download/extract/compile/symlink
    # sequence so two concurrent invocations can't race on the same directory.
    busybox_lock_path = cache_dir / ".kernel-sandbox-busybox-source.lock"
    with file_lock(busybox_lock_path, description="busybox source download/compile"):
        # download busybox-source from latest snapshot archive
        if not archive_path.exists():
            snapshot_url = "https://www.busybox.net/downloads/snapshots/busybox-snapshot.tar.bz2"
            downloader = HTTPDownloader()
            downloader.download_file(snapshot_url, archive_path)

        # unpack busybox-source
        logger.info("Extracting busybox upstream snapshot source tree...")
        try:
            with tarfile.open(archive_path, "r:bz2") as tar:
                members = tar.getmembers()
                if members:
                    root_prefix = members[0].name.split("/")[0] + "/"
                    for member in members:
                        if member.name.startswith(root_prefix):
                            member.name = member.name.removeprefix(root_prefix)
                            tar.extract(member, path=busybox_build_dir)
        except Exception as e:
            raise InitrdBuildError(f"Failed to extract BusyBox archive source tree: {e}")

        try:
            # compile_busybox in a container
            runtime = ContainerEngine.get_container_runtime()
            # FIXME: native arch container compilation is too slow, hence prefering cross_compilation always
            # will revisit this later.

            logger.info(f"Compiling static standalone binary using {runtime} image...")

            with ContainerEngine(
                    runtime=runtime,
                    storage_root=cache_dir / "containers" / "storage",
                    image=container_image,
                    name=f"kernel-sandbox-busybox-{workspace.name[:7]}"
            ) as container_engine:
                # FIXME: compile busybox with the same kernel-build image.
                # busybox compilation with CROSS_COMPILE may fail for ppc64le
                # the containers need cross-ppc64le-glibc-devel package
                # (which can't be found for all distributions).
                # Direct arch compilation works (though slower on non-native hosts).
                # Direct arch compilation:
                #    platform = container_platform_target
                #    cross_compile = ""
                compile_busybox(
                    busybox_build_dir=busybox_build_dir,
                    container_engine=container_engine,
                    platform=container_platform_host,  # above FIXME reasons
                    cross_compile=cross_compile,
                    build_config_patches=build_config_patches
                )

                # store the binary in initrd
                compiled_binary = busybox_build_dir / "busybox"
                if not compiled_binary.exists():
                    raise InitrdBuildError(
                        f"Expected binary output missing post-compilation target path: {compiled_binary}")

                busybox_path = initrd_dir / "bin" / "busybox"
                shutil.copy2(compiled_binary, busybox_path)
                busybox_path.chmod(0o755)

                generate_applet_symlinks(container_engine, busybox_build_dir, container_platform_target, initrd_dir)
        except ContainerRuntimeError as e:
            raise InitrdBuildError(f"Failed to compile busybox: {e}")

    if template_path is None:
        template_path = Path(__file__).resolve().parent.parent / "assets" / "initrd_init.tmpl"
    template_text = _load_template(template_path, "Asset busybox template initialization target")

    init_path = initrd_dir / "custom_init"
    init_path.write_text(
        _render_template(template_text, {"HOST_WORKSPACE_PATH": str(workspace.resolve())}), encoding="utf-8")
    init_path.chmod(0o755)

    # Pack the initrd
    if output_path is None:
        initrd_output = workspace / "tmp" / "initrd_custom.gz"
    else:
        initrd_output = Path(output_path)

    pack_ramdisk_archive(initrd_dir, initrd_output, cpio_bin=cpio_bin)
    return initrd_output


def create_dracut_initrd(
        container_image, container_platform, cache_dir, workspace, kernel_version, module_install_root, output_path
):
    """Generates a full-featured dracut initrd utilizing modules built from the container environment."""
    logger.info("Creating containerized dracut initrd...")
    custom_init_template = _load_template(
        Path(__file__).resolve().parent.parent / "assets" / "initrd_init_full.tmpl", "Dracut custom init template")

    custom_init_dest = module_install_root / "custom_init"
    custom_init_dest.write_text(
        _render_template(custom_init_template, {"HOST_WORKSPACE_PATH": str(workspace.resolve())}), encoding="utf-8")
    custom_init_dest.chmod(0o755)

    if (module_install_root / "usr" / "lib" / "modules" / kernel_version).exists():
        kmoddir = f"/module_root/usr/lib/modules/{kernel_version}"
    else:
        kmoddir = f"/module_root/lib/modules/{kernel_version}"

    dracut_cmd_template = _load_template(
        Path(__file__).resolve().parent.parent / "assets" / "dracut_cmd.tmpl", "Dracut command template")
    dracut_cmd = _render_template(dracut_cmd_template, {"KMODDIR": kmoddir, "KERNEL_VERSION": kernel_version})

    try:
        runtime = ContainerEngine.get_container_runtime()
        with ContainerEngine(
                runtime=runtime,
                storage_root=cache_dir / "containers" / "storage",
                image=container_image,
                name=f"kernel-sandbox-dracut-{workspace.name[:7]}"
        ) as container_engine:
            container_engine.execute_command(
                workspace_path_rw=workspace,
                platform=container_platform,
                env_dict={},
                cmd_str=dracut_cmd,
                workspace_mount="/workspace/",
                extra_volumes={str(module_install_root): "/module_root"},
                tty=True
            )
    except ContainerRuntimeError as e:
        raise InitrdBuildError(f"Failed to run dracut: {e}")

    temp_initrd = module_install_root / "initrd_dracut.gz"
    if temp_initrd.exists():
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(temp_initrd), str(output_path))
        logger.info(f"Dracut initrd created at {output_path}")
        return output_path
    else:
        raise InitrdBuildError("Dracut generation succeeded, but the target initrd_dracut.gz was missing.")
