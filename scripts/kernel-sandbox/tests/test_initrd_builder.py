import gzip
import io
import os
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path

import libs.initrd_builder as initrd_builder
from libs.container_engine import ContainerRuntimeError
from libs.initrd_builder import (
    InitrdBuildError,
    compile_busybox,
    create_busybox_initrd,
    create_dracut_initrd,
    generate_applet_symlinks,
    pack_ramdisk_archive,
)


class MockBusyboxContainerEngine:
    """Helper for ContainerEngine that records execute_command() calls and returns a subprocess.CompletedProcess"""
    last_instance = None

    def __init__(self, runtime, storage_root, image, name=None):
        self.runtime = runtime
        self.storage_root = storage_root
        self.image = image
        self.name = name
        self.calls = []
        MockBusyboxContainerEngine.last_instance = self

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False

    @staticmethod
    def get_container_runtime():
        return "mock-runtime"

    def execute_command(self, **kwargs):
        self.calls.append(kwargs)
        if kwargs.get("workspace_mount") == "/build":
            binary_path = Path(kwargs["workspace_path_rw"]) / "busybox"
            binary_path.write_text("#!/bin/sh\necho mock-busybox\n")
            binary_path.chmod(0o755)
            return subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        return subprocess.CompletedProcess(args=[], returncode=0, stdout="sh\nls\ncat\n", stderr="")


def mock_busybox_tarball(dest_path):
    "Helper for mocking busybox source archive"
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(dest_path, "w:bz2") as tar:
        data = b"mock busybox source\n"
        info = tarfile.TarInfo(name="busybox-1.36.1/README")
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))


class mock_busybox_download:
    def __init__(self):
        self.calls = []

    def download_file(self, url, dest):
        self.calls.append((url, dest))
        mock_busybox_tarball(Path(dest))


class TestCompileBusybox(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.busybox_build_dir = Path(self.tmp_dir.name) / "busybox-source"
        self.busybox_build_dir.mkdir()

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_default_patches(self):
        engine = MockBusyboxContainerEngine(runtime="mock", storage_root="/tmp", image="mock-image")
        compile_busybox(
            busybox_build_dir=self.busybox_build_dir,
            container_engine=engine,
            platform="linux/amd64",
            cross_compile="aarch64-suse-linux-",
            build_config_patches=None
        )
        self.assertEqual(len(engine.calls), 1)
        kwargs = engine.calls[0]
        self.assertEqual(kwargs["workspace_path_rw"], self.busybox_build_dir)
        self.assertEqual(kwargs["platform"], "linux/amd64")
        self.assertEqual(kwargs["workspace_mount"], "/build")

        cmd_str = kwargs["cmd_str"]
        self.assertIn("make defconfig", cmd_str)
        self.assertIn('sed -i "s/# CONFIG_STATIC is not set/CONFIG_STATIC=y/" .config', cmd_str)
        self.assertIn('sed -i "s/CONFIG_TC=y/# CONFIG_TC is not set/" .config', cmd_str)
        self.assertIn('sed -i "s/CONFIG_USE_BB_CRYPT_YES=y/# CONFIG_USE_BB_CRYPT_YES is not set/" .config', cmd_str)
        self.assertIn("make -j$(nproc) CROSS_COMPILE=aarch64-suse-linux- CC=aarch64-suse-linux-gcc HOSTCC=gcc", cmd_str)

    def test_custom_patches(self):
        engine = MockBusyboxContainerEngine(runtime="mock", storage_root="/tmp", image="mock-image")
        compile_busybox(
            busybox_build_dir=self.busybox_build_dir,
            container_engine=engine,
            platform="linux/arm64",
            cross_compile="aarch64-suse-linux-",
            build_config_patches={"CONFIG_FOO": "y", "CONFIG_BAR": "n"}
        )
        cmd_str = engine.calls[0]["cmd_str"]
        self.assertIn('sed -i "s/# CONFIG_FOO is not set/CONFIG_FOO=y/" .config', cmd_str)
        self.assertIn('sed -i "s/CONFIG_BAR=y/# CONFIG_BAR is not set/" .config', cmd_str)


class MockBusyboxContainerEngineExecCmd:
    def __init__(self, mock_make_dir):
        self.mock_make_dir = str(mock_make_dir)

    def execute_command(self, cmd_str, workspace_path_rw, **kwargs):
        env = dict(os.environ)
        env["PATH"] = f"{self.mock_make_dir}:{env.get('PATH', '')}"
        result = subprocess.run(
            ["sh", "-c", cmd_str], cwd=str(workspace_path_rw), env=env, capture_output=True, text=True)
        if result.returncode != 0:
            raise AssertionError(f"exec of cmd_str: {cmd_str} failed: {result.stderr}")
        return result


class TestCompileBusyboxAgainstConfig(unittest.TestCase):
    """Test against sed -i modifications, and container make of busybox"""
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.busybox_build_dir = Path(self.tmp_dir.name) / "busybox-source"
        self.busybox_build_dir.mkdir()

        # mock for what a real `make defconfig` would have produced
        (self.busybox_build_dir / ".config").write_text(
            "# CONFIG_STATIC is not set\n"
            "CONFIG_TC=y\n"
            "CONFIG_USE_BB_CRYPT_YES=y\n"
            "CONFIG_UNRELATED=y\n"
        )

        # mock `make` so distclean/defconfig/the final build step do nothing (no-op)
        # only the sed -i lines in between run for real against the fixture above.
        mock_make_dir = Path(self.tmp_dir.name) / "mockbin"
        mock_make_dir.mkdir()
        mock_make = mock_make_dir / "make"
        mock_make.write_text("#!/bin/sh\nexit 0\n")
        mock_make.chmod(0o755)

        self.engine = MockBusyboxContainerEngineExecCmd(mock_make_dir)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_default_patches_sed_on_config_file(self):
        compile_busybox(
            busybox_build_dir=self.busybox_build_dir,
            container_engine=self.engine,
            platform="linux/amd64",
            cross_compile="",
        )
        config_text = (self.busybox_build_dir / ".config").read_text()
        self.assertIn("CONFIG_STATIC=y", config_text)
        self.assertIn("# CONFIG_TC is not set", config_text)
        self.assertIn("# CONFIG_USE_BB_CRYPT_YES is not set", config_text)
        self.assertNotIn("CONFIG_TC=y", config_text)

    def test_sed_silently_no_ops_when_defconfig_has_drifted(self):
        (self.busybox_build_dir / ".config").write_text(
            "# CONFIG_STATIC is not set\n"
            "CONFIG_TC_RENAMED_UPSTREAM=y\n"  # not the key compile_busybox replaces
        )
        compile_busybox(
            busybox_build_dir=self.busybox_build_dir,
            container_engine=self.engine,
            platform="linux/amd64",
            cross_compile="",
        )
        config_text = (self.busybox_build_dir / ".config").read_text()
        self.assertIn("CONFIG_STATIC=y", config_text)
        self.assertIn("CONFIG_TC_RENAMED_UPSTREAM=y", config_text)


class TestGenerateAppletSymlinks(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.initrd_dir = Path(self.tmp_dir.name) / "initramfs"
        (self.initrd_dir / "bin").mkdir(parents=True)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_creates_real_symlinks_for_each_applet(self):
        engine = MockBusyboxContainerEngine(runtime="mock", storage_root="/tmp", image="mock-image")
        generate_applet_symlinks(engine, Path("/mock/busybox-source"), "linux/amd64", self.initrd_dir)

        for applet in ("sh", "ls", "cat"):
            link = self.initrd_dir / "bin" / applet
            self.assertTrue(link.is_symlink())
            self.assertEqual(os.readlink(link), "busybox")

    def test_skips_existing_link(self):
        """an applet that already exists must not be clobbered with a fresh symlink_to() call."""
        (self.initrd_dir / "bin" / "sh").write_text("already here")
        engine = MockBusyboxContainerEngine(runtime="mock", storage_root="/tmp", image="mock-image")
        generate_applet_symlinks(engine, Path("/mock/busybox-source"), "linux/amd64", self.initrd_dir)
        self.assertFalse((self.initrd_dir / "bin" / "sh").is_symlink())
        self.assertEqual((self.initrd_dir / "bin" / "sh").read_text(), "already here")

    def test_container_runtime_error_wraps_as_initrd_build_error(self):
        class _FailingEngine(MockBusyboxContainerEngine):
            def execute_command(self, **kwargs):
                raise ContainerRuntimeError("busybox --list execution failed")

        engine = _FailingEngine(runtime="mock", storage_root="/tmp", image="mock-image")
        with self.assertRaises(InitrdBuildError) as ctx:
            generate_applet_symlinks(engine, Path("/b"), "linux/amd64", self.initrd_dir)
        self.assertIn("Failed to list busybox applets", str(ctx.exception))


class TestPackRamdiskArchive(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.initrd_dir = Path(self.tmp_dir.name) / "initramfs"
        self.initrd_dir.mkdir()

    def tearDown(self):
        self.tmp_dir.cleanup()

    def mock_cpio(self, script_body, shebang="#!/bin/sh"):
        """mock cpio script"""
        script = Path(self.tmp_dir.name) / "mock-cpio"
        script.write_text(f"{shebang}\n{script_body}\n")
        script.chmod(0o755)
        return str(script)

    def test_success_echoes_stdin_through_real_gzip(self):
        """mock_cpio echoes stdin to stdout, verify subprocess+gzip pipeline works"""
        (self.initrd_dir / "a.txt").write_text("a")
        (self.initrd_dir / "b.txt").write_text("b")
        mock_cpio = self.mock_cpio("cat")

        output = Path(self.tmp_dir.name) / "out" / "initrd.gz"
        pack_ramdisk_archive(self.initrd_dir, output, cpio_bin=mock_cpio)

        with gzip.open(output, "rb") as f:
            content = f.read()
        self.assertIn(b"./a.txt", content)
        self.assertIn(b"./b.txt", content)

    def test_cpio_failure_raises_with_real_stderr(self):
        mock_cpio = self.mock_cpio("echo 'cpio: permission denied' >&2; exit 2")
        output = Path(self.tmp_dir.name) / "out" / "initrd.gz"
        with self.assertRaises(InitrdBuildError) as ctx:
            pack_ramdisk_archive(self.initrd_dir, output, cpio_bin=mock_cpio)
        self.assertIn("permission denied", str(ctx.exception))

    def test_timeout_raises_and_kills_process(self):
        """subprocess.run(timeout=) bounds the whole call and kills the process itself on expiry (automatically)"""
        mock_cpio = self.mock_cpio("sleep 30")
        output = Path(self.tmp_dir.name) / "out" / "initrd.gz"
        with self.assertRaises(InitrdBuildError) as ctx:
            pack_ramdisk_archive(self.initrd_dir, output, cpio_timeout=0.2, cpio_bin=mock_cpio)
        self.assertIn("timed out", str(ctx.exception))

    def test_very_large_tree_packing(self):
        for i in range(2000):
            (self.initrd_dir / f"file_{i}").touch()

        mock_cpio_script = (
            "import sys\n"
            "data = sys.stdin.buffer.read()\n"
            "for path in data.split(b'\\x00'):\n"
            "    if path:\n"
            "        sys.stdout.buffer.write(path + b'-' + (b'X' * 2048))\n"
        )
        mock_cpio = self.mock_cpio(mock_cpio_script, shebang="#!/usr/bin/env python3")

        output = Path(self.tmp_dir.name) / "out" / "initrd.gz"
        pack_ramdisk_archive(self.initrd_dir, output, cpio_timeout=10, cpio_bin=mock_cpio)
        with gzip.open(output, "rb") as f:
            content = f.read()
        self.assertGreater(len(content), 2000 * 2048)


class TestCreateBusyboxInitrd(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.tmp_dir.name) / "workspace"
        self.workspace.mkdir()
        self.cache_dir = Path(self.tmp_dir.name) / "cache"
        self.cache_dir.mkdir()
        self._original_downloader = initrd_builder.HTTPDownloader
        self._original_container_engine = initrd_builder.ContainerEngine
        initrd_builder.HTTPDownloader = mock_busybox_download
        initrd_builder.ContainerEngine = MockBusyboxContainerEngine
        MockBusyboxContainerEngine.last_instance = None
        cpio_script = Path(self.tmp_dir.name) / "mock-cpio"
        cpio_script.write_text("#!/bin/sh\ncat\n")
        cpio_script.chmod(0o755)
        self.mock_cpio = str(cpio_script)

    def tearDown(self):
        initrd_builder.HTTPDownloader = self._original_downloader
        initrd_builder.ContainerEngine = self._original_container_engine
        self.tmp_dir.cleanup()

    def test_full_orchestration_creates_real_initrd_archive(self):
        output_path = Path(self.tmp_dir.name) / "out" / "initrd.gz"
        result = create_busybox_initrd(
            container_image="mock-image",
            container_platform_host="linux/amd64",
            container_platform_target="linux/amd64",
            cross_compile="",
            cache_dir=self.cache_dir,
            workspace=self.workspace,
            output_path=output_path,
            cpio_bin=self.mock_cpio,
        )
        self.assertEqual(result, output_path)
        self.assertTrue(output_path.exists())

        initrd_dir = self.workspace / "tmp" / "initramfs"
        self.assertTrue((initrd_dir / "bin" / "busybox").exists())

        for applet in ("sh", "ls", "cat"):
            link = initrd_dir / "bin" / applet
            self.assertTrue(link.is_symlink())

        with gzip.open(output_path, "rb") as f:
            content = f.read()
        self.assertGreater(len(content), 0)

        compile_call = MockBusyboxContainerEngine.last_instance.calls[0]
        self.assertIn("make defconfig", compile_call["cmd_str"])

    def test_skips_download_when_archive_already_cached(self):
        archive_path = self.cache_dir / "busybox-source" / "busybox-snapshot.tar.bz2"
        mock_busybox_tarball(archive_path)

        calls = []

        class _FailIfCalledDownloader:
            def download_file(self, url, dest):
                calls.append((url, dest))

        initrd_builder.HTTPDownloader = _FailIfCalledDownloader

        output_path = Path(self.tmp_dir.name) / "out" / "initrd.gz"
        create_busybox_initrd(
            container_image="mock-image", container_platform_host="linux/amd64",
            container_platform_target="linux/amd64", cross_compile="",
            cache_dir=self.cache_dir, workspace=self.workspace, output_path=output_path,
            cpio_bin=self.mock_cpio)
        self.assertEqual(calls, [])

    def test_missing_compiled_binary_raises(self):
        """the container 'compiled' successfully but never produced the expected busybox binary file."""
        class _NoOpEngine(MockBusyboxContainerEngine):
            def execute_command(self, **kwargs):
                self.calls.append(kwargs)
                return subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

        initrd_builder.ContainerEngine = _NoOpEngine
        output_path = Path(self.tmp_dir.name) / "out" / "initrd.gz"
        with self.assertRaises(InitrdBuildError) as ctx:
            create_busybox_initrd(
                container_image="mock-image", container_platform_host="linux/amd64",
                container_platform_target="linux/amd64", cross_compile="",
                cache_dir=self.cache_dir, workspace=self.workspace, output_path=output_path)
        self.assertEqual(
            f"Expected binary output missing post-compilation target path: "
            f"{self.cache_dir / 'busybox-source' / 'busybox'}",
            str(ctx.exception)
        )

    def test_compile_failure_wraps_as_initrd_build_error_regression(self):
        """a ContainerRuntimeError during busybox compilation must surface as InitrdBuildError"""
        class _FailingEngine(MockBusyboxContainerEngine):
            def execute_command(self, **kwargs):
                if kwargs.get("workspace_mount") == "/build":
                    raise ContainerRuntimeError("compiler crashed")
                return super().execute_command(**kwargs)

        initrd_builder.ContainerEngine = _FailingEngine
        output_path = Path(self.tmp_dir.name) / "out" / "initrd.gz"
        with self.assertRaises(InitrdBuildError) as ctx:
            create_busybox_initrd(
                container_image="mock-image", container_platform_host="linux/amd64",
                container_platform_target="linux/amd64", cross_compile="",
                cache_dir=self.cache_dir, workspace=self.workspace, output_path=output_path)
        self.assertEqual("Failed to compile busybox: compiler crashed", str(ctx.exception))


class MockDracutContainerEngine:
    last_instance = None

    def __init__(self, runtime, storage_root, image, name=None):
        self.runtime = runtime
        self.storage_root = storage_root
        self.image = image
        self.name = name
        self.calls = []
        MockDracutContainerEngine.last_instance = self

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False

    @staticmethod
    def get_container_runtime():
        return "mock-runtime"

    def execute_command(self, **kwargs):
        self.calls.append(kwargs)
        module_root = Path(next(iter(kwargs["extra_volumes"])))
        (module_root / "initrd_dracut.gz").write_bytes(b"mock-dracut-initrd-bytes")
        return subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")


class TestCreateDracutInitrd(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.tmp_dir.name) / "workspace"
        self.workspace.mkdir()
        self.cache_dir = Path(self.tmp_dir.name) / "cache"
        self.module_install_root = Path(self.tmp_dir.name) / "modules"
        self.module_install_root.mkdir()
        self._original_container_engine = initrd_builder.ContainerEngine
        initrd_builder.ContainerEngine = MockDracutContainerEngine
        MockDracutContainerEngine.last_instance = None

    def tearDown(self):
        initrd_builder.ContainerEngine = self._original_container_engine
        self.tmp_dir.cleanup()

    def test_full_orchestration_moves_real_dracut_output(self):
        kernel_version = "6.12.0-default"
        (self.module_install_root / "lib" / "modules" / kernel_version).mkdir(parents=True)
        output_path = Path(self.tmp_dir.name) / "out" / "initrd_dracut.gz"

        result = create_dracut_initrd(
            container_image="mock-image", container_platform="linux/amd64",
            cache_dir=self.cache_dir, workspace=self.workspace,
            kernel_version=kernel_version, module_install_root=self.module_install_root,
            output_path=output_path
        )
        self.assertEqual(result, output_path)
        self.assertEqual(output_path.read_bytes(), b"mock-dracut-initrd-bytes")

        custom_init = self.module_install_root / "custom_init"
        self.assertIn(str(self.workspace.resolve()), custom_init.read_text())

        cmd_str = MockDracutContainerEngine.last_instance.calls[0]["cmd_str"]
        self.assertIn(f"/module_root/lib/modules/{kernel_version}", cmd_str)

    def test_usr_lib_modules_path_detected_when_present(self):
        kernel_version = "6.12.0-default"
        (self.module_install_root / "usr" / "lib" / "modules" / kernel_version).mkdir(parents=True)
        output_path = Path(self.tmp_dir.name) / "out" / "initrd_dracut.gz"

        create_dracut_initrd(
            container_image="mock-image", container_platform="linux/amd64",
            cache_dir=self.cache_dir, workspace=self.workspace,
            kernel_version=kernel_version, module_install_root=self.module_install_root,
            output_path=output_path
        )
        cmd_str = MockDracutContainerEngine.last_instance.calls[0]["cmd_str"]
        self.assertIn(f"/module_root/usr/lib/modules/{kernel_version}", cmd_str)

    def test_missing_output_file_raises(self):
        """dracut 'succeeds' (no exception) but never produced the expected initrd_dracut.gz"""
        class _NoOpEngine(MockDracutContainerEngine):
            def execute_command(self, **kwargs):
                self.calls.append(kwargs)
                return subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

        initrd_builder.ContainerEngine = _NoOpEngine
        output_path = Path(self.tmp_dir.name) / "out" / "initrd_dracut.gz"
        with self.assertRaises(InitrdBuildError) as ctx:
            create_dracut_initrd(
                container_image="mock-image", container_platform="linux/amd64",
                cache_dir=self.cache_dir, workspace=self.workspace,
                kernel_version="6.12.0-default", module_install_root=self.module_install_root,
                output_path=output_path)
        self.assertEqual("Dracut generation succeeded, but the target initrd_dracut.gz was missing.", str(ctx.exception))

    def test_container_runtime_error_wraps_as_initrd_build_error_regression(self):
        class _FailingEngine(MockDracutContainerEngine):
            def execute_command(self, **kwargs):
                raise ContainerRuntimeError("dracut crashed")

        initrd_builder.ContainerEngine = _FailingEngine
        output_path = Path(self.tmp_dir.name) / "out" / "initrd_dracut.gz"
        with self.assertRaises(InitrdBuildError) as ctx:
            create_dracut_initrd(
                container_image="mock-image", container_platform="linux/amd64",
                cache_dir=self.cache_dir, workspace=self.workspace,
                kernel_version="6.12.0-default", module_install_root=self.module_install_root,
                output_path=output_path)
        self.assertIn("dracut crashed", str(ctx.exception))
