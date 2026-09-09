import subprocess
import tempfile
import unittest
from pathlib import Path

import pipeline_engines
from libs.cache_metadata import read_cache_metadata
from libs.container_engine import ContainerRuntimeError
from libs.image_customizer import DependencyError, ImageCustomizationError
from libs.initrd_builder import InitrdBuildError
from libs.pipeline_context import FastModeContext, RpmModeContext
from libs.virtual_engine import VirtualEngineError
from pipeline_engines import BootEngine, BuildEngine, ImagePreparer, PipelineError


def _write_script(path, body, shebang="#!/bin/sh"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{shebang}\n{body}\n")
    path.chmod(0o755)
    return path


class MockContainerEngine:
    """Helper for ContainerEngine that records execute_command() calls, pull_calls"""
    last_instance = None

    def __init__(self, runtime, storage_root, image, name=None):
        self.runtime = runtime
        self.storage_root = storage_root
        self.image = image
        self.name = name
        self.calls = []
        self.pull_calls = 0
        self.remove_container_calls = 0
        self.fail_pull_with = None
        self.fail_execute_with = None
        MockContainerEngine.last_instance = self

    def __enter__(self):
        self.remove_container()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.remove_container()
        return False

    @staticmethod
    def get_container_runtime():
        return "mock-runtime"

    def pull_image(self, timeout=None):
        self.pull_calls += 1
        if self.fail_pull_with:
            raise self.fail_pull_with

    def execute_command(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail_execute_with:
            raise self.fail_execute_with

    def remove_container(self):
        self.remove_container_calls += 1


class TestBuildEngineExecuteFast(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.tmp_dir.name) / "workspace"
        self.workspace.mkdir()
        self.cache_dir = Path(self.tmp_dir.name) / "cache"
        self.cache_dir.mkdir()
        self._original_container_engine = pipeline_engines.ContainerEngine
        pipeline_engines.ContainerEngine = MockContainerEngine
        MockContainerEngine.last_instance = None

    def tearDown(self):
        pipeline_engines.ContainerEngine = self._original_container_engine
        self.tmp_dir.cleanup()

    def _ctx(self, **overrides):
        fields = dict(
            workspace=self.workspace, build_root=self.workspace / "tmp", cache_dir=self.cache_dir,
            commit_hash="abc1234def", arch="x86_64", config_flavor="default", mode="fast",
            refresh_cache=False, use_busybox_initrd=True, qemu_bin="qemu-system-x86_64",
            extra_qemu="", host_arch="x86_64", ssh_enabled=False,
            kernel_image_name="bzImage", build_image_name="bzImage", linux_arch="x86_64",
            boot_arch="x86", cross_compile="", target_arch_platform="linux/amd64",
            host_arch_platform="linux/amd64", container_image="mock-image", cc="gcc", host_cc="gcc",
            enable_configs=[], disable_configs=[],
        )
        fields.update(overrides)
        return FastModeContext(**fields)

    def _write_config(self, ctx):
        (self.workspace / "config" / ctx.arch / ctx.config_flavor).mkdir(parents=True)

    def _write_sequence_patch(self, ctx, extra_body=""):
        sp_dir = self.workspace / f"kernel-sandbox-sp-{ctx.commit_hash[:7]}-{ctx.arch}-{ctx.config_flavor}" / "current"

        def _make(*_args, **_kwargs):
            sp_dir.mkdir(parents=True, exist_ok=True)
            (sp_dir / ".config").write_text("# mock config\n")

        # sequence-patch applies and copies "current" dir + .config
        script = _write_script(
            self.workspace / "scripts" / "sequence-patch",
            f"mkdir -p '{sp_dir}'\ntouch '{sp_dir}/.config'\n{extra_body}"
        )
        return script

    def test_missing_config_path_raises(self):
        ctx = self._ctx()
        with self.assertRaisesRegex(PipelineError, r"^Kernel configuration missing in workspace:"):
            BuildEngine()._execute_fast(ctx)

    def test_cache_hit_skips_container_entirely(self):
        """cache-hit must return before touching ContainerEngine"""
        ctx = self._ctx()
        self._write_config(ctx)
        artifacts_dir = ctx.artifacts_dir
        artifacts_dir.mkdir(parents=True)
        (artifacts_dir / ctx.kernel_image_name).write_text("cached-kernel")
        (artifacts_dir / "initrd_custom.gz").write_text("cached-initrd")

        BuildEngine()._execute_fast(ctx)
        self.assertIsNone(MockContainerEngine.last_instance)

    def test_sequence_patch_failure_raises_pipeline_error(self):
        ctx = self._ctx()
        self._write_config(ctx)
        _write_script(self.workspace / "scripts" / "sequence-patch", "exit 3")

        with self.assertRaises(PipelineError) as ctx_err:
            BuildEngine()._execute_fast(ctx)
        self.assertEqual("sequence-patch failed with exit code 3", str(ctx_err.exception))

    def test_missing_config_after_sequence_patch_raises(self):
        ctx = self._ctx()
        self._write_config(ctx)
        _write_script(self.workspace / "scripts" / "sequence-patch", "exit 0")  # never creates .config

        with self.assertRaisesRegex(PipelineError, r"^\.config not found after sequence-patch at "):
            BuildEngine()._execute_fast(ctx)

    def test_pull_image_failure_propagates_as_container_runtime_error(self):
        ctx = self._ctx()
        self._write_config(ctx)
        self._write_sequence_patch(ctx)

        class _FailingPullEngine(MockContainerEngine):
            def __init__(self, runtime, storage_root, image, name=None):
                super().__init__(runtime, storage_root, image, name=name)
                self.fail_pull_with = ContainerRuntimeError("registry unreachable")

        pipeline_engines.ContainerEngine = _FailingPullEngine
        with self.assertRaises(ContainerRuntimeError) as ctx_err:
            BuildEngine()._execute_fast(ctx)
        self.assertEqual("registry unreachable", str(ctx_err.exception))

    def test_execute_command_failure_propagates_as_container_runtime_error(self):
        ctx = self._ctx()
        self._write_config(ctx)
        self._write_sequence_patch(ctx)

        class _FailingExecuteEngine(MockContainerEngine):
            def __init__(self, runtime, storage_root, image, name=None):
                super().__init__(runtime, storage_root, image, name=name)
                self.fail_execute_with = ContainerRuntimeError("compiler crashed")

        pipeline_engines.ContainerEngine = _FailingExecuteEngine
        with self.assertRaises(ContainerRuntimeError) as ctx_err:
            BuildEngine()._execute_fast(ctx)
        self.assertEqual("compiler crashed", str(ctx_err.exception))
        # __exit__ must still fire and clean up even though execute_command() raised
        self.assertEqual(MockContainerEngine.last_instance.remove_container_calls, 2)

    def test_container_cleanup_runs_on_success_too(self):
        """__enter__ removes any stale same-named leftover before starting,
        __exit__ removes the fresh one after"""
        ctx = self._ctx()
        self._write_config(ctx)
        self._write_sequence_patch(ctx)
        sp_dir = self.workspace / f"kernel-sandbox-sp-{ctx.commit_hash[:7]}-{ctx.arch}-{ctx.config_flavor}" / "current"
        built_kernel = sp_dir / "arch" / ctx.boot_arch / "boot" / ctx.build_image_name
        built_kernel.parent.mkdir(parents=True)
        built_kernel.write_text("mock-bzImage-bytes")

        BuildEngine()._execute_fast(ctx)

        self.assertEqual(MockContainerEngine.last_instance.remove_container_calls, 2)

    def test_missing_built_kernel_after_successful_compile_raises(self):
        ctx = self._ctx()
        self._write_config(ctx)
        self._write_sequence_patch(ctx)
        # mock container "compiles" but never produces arch/<boot_arch>/boot/<image>
        with self.assertRaisesRegex(PipelineError, r"^Built kernel image missing \(checked at - "):
            BuildEngine()._execute_fast(ctx)

    def test_successful_build_archives_kernel_to_cache(self):
        ctx = self._ctx()
        self._write_config(ctx)
        self._write_sequence_patch(ctx)
        sp_dir = self.workspace / f"kernel-sandbox-sp-{ctx.commit_hash[:7]}-{ctx.arch}-{ctx.config_flavor}" / "current"
        built_kernel = sp_dir / "arch" / ctx.boot_arch / "boot" / ctx.build_image_name
        built_kernel.parent.mkdir(parents=True)
        built_kernel.write_text("mock-bzImage-bytes")

        BuildEngine()._execute_fast(ctx)

        cached = ctx.artifacts_dir / ctx.kernel_image_name
        self.assertTrue(cached.exists())
        self.assertEqual(cached.read_text(), "mock-bzImage-bytes")
        self.assertEqual(MockContainerEngine.last_instance.pull_calls, 1)


class TestBuildEngineExecuteRpm(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.tmp_dir.name) / "workspace"
        self.workspace.mkdir()
        self.cache_dir = Path(self.tmp_dir.name) / "cache"
        self.cache_dir.mkdir()
        self.rpm_build_root = Path(self.tmp_dir.name) / "build-root"

    def tearDown(self):
        self.tmp_dir.cleanup()

    def _ctx(self, **overrides):
        fields = dict(
            workspace=self.workspace, build_root=self.workspace / "tmp", cache_dir=self.cache_dir,
            commit_hash="01ed33dabc", arch="x86_64", config_flavor="default", mode="rpm",
            refresh_cache=False, use_busybox_initrd=False, qemu_bin="qemu-system-x86_64",
            extra_qemu="", host_arch="x86_64", ssh_enabled=False,
            ibs_project="SUSE:SLFO:Main", obs_project="openSUSE:Factory", rpm_arch="x86_64",
            rpm_build_root=self.rpm_build_root,
        )
        fields.update(overrides)
        return RpmModeContext(**fields)

    def test_cache_hit_skips_osc_build(self):
        ctx = self._ctx()
        rpm_cache_dir = ctx.artifacts_dir / "rpms"
        rpm_cache_dir.mkdir(parents=True)
        (rpm_cache_dir / f"kernel-default-6.12.0-0.g{ctx.commit_hash[:7]}.x86_64.rpm").touch()

        called = []
        BuildEngine()._run_osc_build = lambda ctx, git_marker: called.append(True)
        BuildEngine()._execute_rpm(ctx)
        self.assertEqual(called, [])

    def test_no_rpms_found_after_build_raises(self):
        ctx = self._ctx()
        engine = BuildEngine()
        engine._run_osc_build = lambda ctx, git_marker: None  # "succeeds" but produces nothing
        with self.assertRaisesRegex(PipelineError, r"^No RPMs found in .* after successful osc build"):
            engine._execute_rpm(ctx)

    def test_successful_build_harvests_matching_rpms_only(self):
        ctx = self._ctx()
        build_root_rpms = self.rpm_build_root / "home" / "abuild" / "rpmbuild" / "RPMS" / ctx.rpm_arch
        build_root_rpms.mkdir(parents=True)
        matching = build_root_rpms / f"kernel-default-6.12.0-0.g{ctx.commit_hash[:7]}.x86_64.rpm"
        matching.write_text("rpm-bytes")
        (build_root_rpms / "unrelated-package-1.0.x86_64.rpm").write_text("unrelated")

        engine = BuildEngine()
        engine._run_osc_build = lambda ctx, git_marker: None
        engine._execute_rpm(ctx)

        cached = ctx.artifacts_dir / "rpms" / matching.name
        self.assertTrue(cached.exists())
        self.assertEqual(len(list((ctx.artifacts_dir / "rpms").glob("*.rpm"))), 1)


class TestRunOscBuild(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.tmp_dir.name) / "workspace"
        self.workspace.mkdir()

    def tearDown(self):
        self.tmp_dir.cleanup()

    def _ctx(self, **overrides):
        fields = dict(
            workspace=self.workspace, build_root=self.workspace / "tmp", cache_dir=Path(self.tmp_dir.name) / "cache",
            commit_hash="abc1234def", arch="x86_64", config_flavor="default", mode="rpm",
            refresh_cache=False, use_busybox_initrd=False, qemu_bin="qemu-system-x86_64",
            extra_qemu="", host_arch="x86_64", ssh_enabled=False,
            ibs_project=None, obs_project=None,
            ibs_api_url="https://api.example-ibs.test", obs_api_url="https://api.example-obs.test",
            rpm_arch="x86_64", rpm_build_root=Path(self.tmp_dir.name) / "build-root",
        )
        fields.update(overrides)
        return RpmModeContext(**fields)

    def _mock_ibs_reachable(self, reachable):
        original = pipeline_engines.urllib.request.urlopen
        if reachable:
            response = type(
                "_MockUrlopenResponse", (),
                {"status": 200, "__enter__": lambda self: self, "__exit__": lambda self, *exc: False}
            )()
            pipeline_engines.urllib.request.urlopen = lambda *args, **kwargs: response
        else:
            def _unreachable(*args, **kwargs):
                raise pipeline_engines.urllib.error.URLError("no network in this sandbox")
            pipeline_engines.urllib.request.urlopen = _unreachable
        self.addCleanup(lambda: setattr(pipeline_engines.urllib.request, "urlopen", original))

    def test_missing_target_project_raises(self):
        ctx = self._ctx(ibs_project=None, obs_project=None)
        self._mock_ibs_reachable(False)
        with self.assertRaisesRegex(PipelineError, r"^Target project \(IBS\|OBS\) not specified for"):
            BuildEngine()._run_osc_build(ctx, "-marker")

    def test_tar_up_failure_raises_pipeline_error(self):
        ctx = self._ctx(obs_project="openSUSE:Factory", ibs_project="SUSE:SLFO:Main")
        self._mock_ibs_reachable(False)
        _write_script(self.workspace / "scripts" / "tar-up", "exit 5")

        with self.assertRaises(PipelineError) as ctx_err:
            BuildEngine()._run_osc_build(ctx, "-marker")
        self.assertEqual("Host RPM build failed with exit code 5", str(ctx_err.exception))

    def test_ibs_reachable_but_not_configured_falls_back_to_obs(self):
        ctx = self._ctx(ibs_project=None, obs_project="openSUSE:Factory")
        self._mock_ibs_reachable(True)
        _write_script(self.workspace / "scripts" / "tar-up", "exit 5")

        with self.assertRaises(PipelineError) as ctx_err:
            BuildEngine()._run_osc_build(ctx, "-marker")
        self.assertEqual("Host RPM build failed with exit code 5", str(ctx_err.exception))

    def test_ibs_reachable_and_configured_prefers_ibs(self):
        ctx = self._ctx(ibs_project="SUSE:SLFO:Main", obs_project="openSUSE:Factory")
        self._mock_ibs_reachable(True)
        _write_script(self.workspace / "scripts" / "tar-up", "exit 0")

        captured = {}
        original_run = pipeline_engines.subprocess.run

        def _mock_run(cmd, **kwargs):
            if cmd[0] == "osc":
                captured["cmd"] = cmd
                return subprocess.CompletedProcess(cmd, 0)
            return original_run(cmd, **kwargs)

        pipeline_engines.subprocess.run = _mock_run
        try:
            BuildEngine()._run_osc_build(ctx, "-marker")  # must not raise
        finally:
            pipeline_engines.subprocess.run = original_run

        self.assertIn("https://api.example-ibs.test", captured["cmd"])
        self.assertIn("--alternative-project=SUSE:SLFO:Main", captured["cmd"])

    def test_ibs_unreachable_and_configured_falls_back_to_obs(self):
        ctx = self._ctx(ibs_project="SUSE:SLFO:Main", obs_project="openSUSE:Factory")
        self._mock_ibs_reachable(False)
        _write_script(self.workspace / "scripts" / "tar-up", "exit 0")

        captured = {}
        original_run = pipeline_engines.subprocess.run

        def _mock_run(cmd, **kwargs):
            if cmd[0] == "osc":
                captured["cmd"] = cmd
                return subprocess.CompletedProcess(cmd, 0)
            return original_run(cmd, **kwargs)

        pipeline_engines.subprocess.run = _mock_run
        try:
            BuildEngine()._run_osc_build(ctx, "-marker")  # must not raise
        finally:
            pipeline_engines.subprocess.run = original_run

        self.assertIn("https://api.example-obs.test", captured["cmd"])
        self.assertIn("--alternative-project=openSUSE:Factory", captured["cmd"])


class TestInstallModules(unittest.TestCase):
    def test_success(self):
        engine_calls = []

        class _Engine:
            def execute_command(self, **kwargs):
                engine_calls.append(kwargs)

        BuildEngine().install_modules(
            Path("/workspace"), _Engine(), "linux/amd64", {}, "", "gcc", "gcc", Path("/mods"), "x86_64")
        self.assertEqual(len(engine_calls), 1)
        self.assertIn("modules_install", engine_calls[0]["cmd_str"])

    def test_failure_propagates_as_container_runtime_error(self):
        class _FailingEngine:
            def execute_command(self, **kwargs):
                raise ContainerRuntimeError("module build crashed")

        with self.assertRaises(ContainerRuntimeError) as ctx_err:
            BuildEngine().install_modules(
                Path("/workspace"), _FailingEngine(), "linux/amd64", {}, "", "gcc", "gcc", Path("/mods"), "x86_64")
        self.assertEqual("module build crashed", str(ctx_err.exception))


class TestImagePreparer(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.tmp_dir.name) / "workspace"
        self.workspace.mkdir()
        self.cache_dir = Path(self.tmp_dir.name) / "cache"
        self.cache_dir.mkdir()

    def tearDown(self):
        self.tmp_dir.cleanup()

    def _rpm_ctx(self, **overrides):
        fields = dict(
            workspace=self.workspace, build_root=self.workspace / "tmp", cache_dir=self.cache_dir,
            commit_hash="abc1234def", arch="x86_64", config_flavor="default", mode="rpm",
            refresh_cache=False, use_busybox_initrd=False, qemu_bin="qemu-system-x86_64",
            extra_qemu="", host_arch="x86_64", ssh_enabled=False, rpm_arch="x86_64",
            cow_image=Path(self.tmp_dir.name) / "sandbox.qcow2",
        )
        fields.update(overrides)
        return RpmModeContext(**fields)

    def _fast_ctx(self, **overrides):
        fields = dict(
            workspace=self.workspace, build_root=self.workspace / "tmp", cache_dir=self.cache_dir,
            commit_hash="abc1234def", arch="x86_64", config_flavor="default", mode="fast",
            refresh_cache=False, use_busybox_initrd=True, qemu_bin="qemu-system-x86_64",
            extra_qemu="", host_arch="x86_64", ssh_enabled=False,
            container_image="mock-image", target_arch_platform="linux/amd64", host_arch_platform="linux/amd64",
            cross_compile="",
        )
        fields.update(overrides)
        return FastModeContext(**fields)

    def test_rpm_mode_failure_propagates_as_image_customization_error(self):
        ctx = self._rpm_ctx()  # no cached RPMs -> install_rpms_to_image raises directly
        with self.assertRaisesRegex(ImageCustomizationError, r"^RPM cache directory does not exist"):
            ImagePreparer().execute(ctx)

    def test_rpm_mode_dependency_error_propagates(self):
        ctx = self._rpm_ctx()
        original = pipeline_engines.install_rpms_to_image

        def _raise_dependency_error(*args, **kwargs):
            raise DependencyError("virt-customize not found")

        pipeline_engines.install_rpms_to_image = _raise_dependency_error
        try:
            with self.assertRaises(DependencyError) as ctx_err:
                ImagePreparer().execute(ctx)
            self.assertEqual("virt-customize not found", str(ctx_err.exception))
        finally:
            pipeline_engines.install_rpms_to_image = original

    def test_fast_mode_cache_hit_skips_initrd_build(self):
        ctx = self._fast_ctx()
        ctx.artifacts_dir.mkdir(parents=True)
        (ctx.artifacts_dir / "initrd_custom.gz").write_text("cached-initrd")

        original = pipeline_engines.create_busybox_initrd

        def _mock_raise_create_busybox_initrd(**kwargs):
            raise AssertionError("create_busybox_initrd should not be called when a cache hit occurs")

        pipeline_engines.create_busybox_initrd = _mock_raise_create_busybox_initrd
        try:
            ImagePreparer().execute(ctx)
        finally:
            pipeline_engines.create_busybox_initrd = original

    def test_fast_mode_busybox_build_failure_propagates_as_initrd_build_error(self):
        ctx = self._fast_ctx(use_busybox_initrd=True)
        original = pipeline_engines.create_busybox_initrd

        def _mock_raise_create_busybox_initrd(**kwargs):
            raise InitrdBuildError("busybox compile failed")

        pipeline_engines.create_busybox_initrd = _mock_raise_create_busybox_initrd
        try:
            with self.assertRaises(InitrdBuildError) as ctx_err:
                ImagePreparer().execute(ctx)
            self.assertEqual("busybox compile failed", str(ctx_err.exception))
        finally:
            pipeline_engines.create_busybox_initrd = original

    def test_dracut_mode_missing_modules_raises(self):
        ctx = self._fast_ctx(use_busybox_initrd=False)
        with self.assertRaisesRegex(PipelineError, r"^Kernel modules not found at .* You must complete the build phase"):
            ImagePreparer().execute(ctx)

    def test_dracut_mode_missing_kver_file_raises(self):
        ctx = self._fast_ctx(use_busybox_initrd=False)
        (ctx.artifacts_dir / "modules").mkdir(parents=True)
        with self.assertRaisesRegex(PipelineError, r"^Cannot determine exact kernel version for Dracut: .* does not exist."):
            ImagePreparer().execute(ctx)

    def test_writes_cache_metadata_for_rpm_mode_even_when_install_fails(self):
        """Metadata is written unconditionally on a build whose image phase failed."""
        ctx = self._rpm_ctx()
        with self.assertRaises(ImageCustomizationError):
            ImagePreparer().execute(ctx)

        metadata = read_cache_metadata(ctx.artifacts_dir)
        self.assertEqual(metadata["mode"], "rpm")
        self.assertEqual(metadata["arch"], "x86_64")
        self.assertEqual(metadata["config_flavor"], "default")
        self.assertEqual(metadata["commit_hash"], "abc1234def")
        self.assertEqual(metadata["rpm_arch"], "x86_64")
        self.assertIsNone(metadata["kernel_image_name"])

    def test_writes_cache_metadata_for_fast_mode_on_cache_hit(self):
        ctx = self._fast_ctx(kernel_image_name="vmlinuz")
        ctx.artifacts_dir.mkdir(parents=True)
        (ctx.artifacts_dir / "initrd_custom.gz").write_text("cached-initrd")

        ImagePreparer().execute(ctx)

        metadata = read_cache_metadata(ctx.artifacts_dir)
        self.assertEqual(metadata["mode"], "fast")
        self.assertEqual(metadata["kernel_image_name"], "vmlinuz")
        self.assertIsNone(metadata["rpm_arch"])


class _MockVirtualMachine:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.proc = None
        self.spawn_calls = []
        self.verify_health_raises = None
        self.wait_called = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def build_command(self):
        return [self.kwargs.get("qemu_bin", "qemu"), "-m", "4096"]

    def spawn(self, **kwargs):
        self.spawn_calls.append(kwargs)

        class _Proc:
            pid = 4242

            def wait(self_inner):
                self.wait_called = True

        self.proc = _Proc()
        return self.proc

    def verify_health(self, delay=1.0):
        if self.verify_health_raises:
            raise self.verify_health_raises
        return True


class TestBootEngine(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.tmp_dir.name) / "workspace"
        self.workspace.mkdir()
        self.cache_dir = Path(self.tmp_dir.name) / "cache"
        self.cache_dir.mkdir()
        self._original_vm = pipeline_engines.VirtualMachine
        pipeline_engines.VirtualMachine = _MockVirtualMachine

    def tearDown(self):
        pipeline_engines.VirtualMachine = self._original_vm
        self.tmp_dir.cleanup()

    def _fast_ctx(self, **overrides):
        fields = dict(
            workspace=self.workspace, build_root=self.workspace / "tmp", cache_dir=self.cache_dir,
            commit_hash="abc1234def", arch="x86_64", config_flavor="default", mode="fast",
            refresh_cache=False, use_busybox_initrd=True, qemu_bin="qemu-system-x86_64",
            extra_qemu="", host_arch="x86_64", ssh_enabled=False, kernel_image_name="bzImage",
        )
        fields.update(overrides)
        return FastModeContext(**fields)

    def test_fast_mode_missing_kernel_raises(self):
        ctx = self._fast_ctx()
        with self.assertRaisesRegex(PipelineError, r"^Built kernel image not found at "):
            BootEngine().execute(ctx)

    def test_fast_mode_missing_initrd_raises(self):
        ctx = self._fast_ctx()
        ctx.artifacts_dir.mkdir(parents=True)
        (ctx.artifacts_dir / ctx.kernel_image_name).write_text("kernel")
        with self.assertRaisesRegex(PipelineError, r"^Initrd not found at "):
            BootEngine().execute(ctx)

    def test_fast_mode_foreground_boot_succeeds(self):
        ctx = self._fast_ctx()
        ctx.artifacts_dir.mkdir(parents=True)
        (ctx.artifacts_dir / ctx.kernel_image_name).write_text("kernel")
        (ctx.artifacts_dir / "initrd_custom.gz").write_text("initrd")

        BootEngine().execute(ctx)  # must not raise

    def test_fast_mode_keyboard_interrupt_is_handled_gracefully(self):
        ctx = self._fast_ctx()
        ctx.artifacts_dir.mkdir(parents=True)
        (ctx.artifacts_dir / ctx.kernel_image_name).write_text("kernel")
        (ctx.artifacts_dir / "initrd_custom.gz").write_text("initrd")

        class _InterruptingVM(_MockVirtualMachine):
            def spawn(self, **kwargs):
                raise KeyboardInterrupt()

        pipeline_engines.VirtualMachine = _InterruptingVM
        BootEngine().execute(ctx)  # must not propagate KeyboardInterrupt

    def test_fast_mode_ssh_flag_auto_connects(self):
        """--ssh mode in fast mode should take boot phase via background-spawn/wait/auto-connect"""
        ctx = self._fast_ctx(ssh_enabled=True)
        ctx.artifacts_dir.mkdir(parents=True)
        (ctx.artifacts_dir / ctx.kernel_image_name).write_text("kernel")
        (ctx.artifacts_dir / "initrd_custom.gz").write_text("initrd")

        connect_calls = []
        original_wait = pipeline_engines.wait_for_ssh_ready
        original_connect = pipeline_engines.connect_ssh_and_wait
        pipeline_engines.wait_for_ssh_ready = lambda port, timeout: True
        pipeline_engines.connect_ssh_and_wait = lambda port: connect_calls.append(port) or True
        try:
            BootEngine().execute(ctx)  # must not raise
        finally:
            pipeline_engines.wait_for_ssh_ready = original_wait
            pipeline_engines.connect_ssh_and_wait = original_connect

        self.assertEqual(connect_calls, [2222])

    def test_fast_mode_without_ssh_flag_stays_foreground(self):
        ctx = self._fast_ctx(ssh_enabled=False)
        ctx.artifacts_dir.mkdir(parents=True)
        (ctx.artifacts_dir / ctx.kernel_image_name).write_text("kernel")
        (ctx.artifacts_dir / "initrd_custom.gz").write_text("initrd")

        def _fail_if_called(port):
            raise AssertionError("connect_ssh_and_wait must not be called without --ssh in fast mode")

        original_connect = pipeline_engines.connect_ssh_and_wait
        pipeline_engines.connect_ssh_and_wait = _fail_if_called
        try:
            BootEngine().execute(ctx)  # must not raise
        finally:
            pipeline_engines.connect_ssh_and_wait = original_connect

    def test_rpm_mode_auto_ssh_success(self):
        ctx = self._fast_ctx(mode="rpm", ssh_enabled=False)
        ctx.cow_image = Path(self.tmp_dir.name) / "sandbox.qcow2"
        ctx.cow_image.write_text("qcow2-bytes")

        original_wait = pipeline_engines.wait_for_ssh_ready
        original_connect = pipeline_engines.connect_ssh_and_wait
        pipeline_engines.wait_for_ssh_ready = lambda port, timeout: True
        pipeline_engines.connect_ssh_and_wait = lambda port: True
        try:
            BootEngine().execute(ctx)  # must not raise
        finally:
            pipeline_engines.wait_for_ssh_ready = original_wait
            pipeline_engines.connect_ssh_and_wait = original_connect

    def test_rpm_mode_ssh_never_ready_raises_and_captures_logfd(self):
        ctx = self._fast_ctx(mode="rpm", ssh_enabled=False)
        ctx.cow_image = Path(self.tmp_dir.name) / "sandbox.qcow2"
        ctx.cow_image.write_text("qcow2-bytes")

        class _LogFDWriting(_MockVirtualMachine):
            def spawn(self, log_fd=None, **kwargs):
                if log_fd:
                    log_fd.write("qemu: guest boot hung waiting for network\n")
                    log_fd.flush()
                self.spawn_calls.append({"log_fd": log_fd})

                class _Proc:
                    pid = 4242

                    def wait(self_inner):
                        pass

                self.proc = _Proc()
                return self.proc

        pipeline_engines.VirtualMachine = _LogFDWriting
        original_wait = pipeline_engines.wait_for_ssh_ready
        pipeline_engines.wait_for_ssh_ready = lambda port, timeout: False
        try:
            with self.assertRaises(PipelineError) as ctx_err:
                BootEngine().execute(ctx)
            self.assertEqual("SSH did not become available - VM may have failed to boot", str(ctx_err.exception))
        finally:
            pipeline_engines.wait_for_ssh_ready = original_wait

    def test_rpm_mode_verify_health_failure_propagates_as_virtual_engine_error(self):
        ctx = self._fast_ctx(mode="rpm", ssh_enabled=False)
        ctx.cow_image = Path(self.tmp_dir.name) / "sandbox.qcow2"
        ctx.cow_image.write_text("qcow2-bytes")

        class _CrashedQEMUInstance(_MockVirtualMachine):
            def spawn(self, **kwargs):
                self.spawn_calls.append(kwargs)
                self.verify_health_raises = VirtualEngineError("QEMU crashed immediately")

                class _Proc:
                    pid = 1

                    def wait(self_inner):
                        pass
                self.proc = _Proc()
                return self.proc

        pipeline_engines.VirtualMachine = _CrashedQEMUInstance
        with self.assertRaises(VirtualEngineError) as ctx_err:
            BootEngine().execute(ctx)
        self.assertEqual("QEMU crashed immediately", str(ctx_err.exception))
