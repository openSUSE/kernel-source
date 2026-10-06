import unittest
from pathlib import Path

from libs.pipeline_context import FastModeContext, PipelineContext, RpmModeContext


def _common_fields(**overrides):
    fields = dict(
        workspace=Path("/workspace"), build_root=Path("/workspace/tmp"), cache_dir=Path("/cache"),
        commit_hash="abc1234", arch="x86_64", config_flavor="default", mode="fast",
        refresh_cache=False, use_busybox_initrd=True, qemu_bin="qemu-system-x86_64",
        extra_qemu="", host_arch="x86_64", ssh_enabled=False,
    )
    fields.update(overrides)
    return fields


class TestPipelineContext(unittest.TestCase):
    def test_stores_all_common_fields(self):
        ctx = PipelineContext(**_common_fields())
        self.assertEqual(ctx.workspace, Path("/workspace"))
        self.assertEqual(ctx.arch, "x86_64")
        self.assertEqual(ctx.mode, "fast")
        self.assertTrue(ctx.use_busybox_initrd)

    def test_artifacts_dir_composes_expected_layout(self):
        ctx = PipelineContext(**_common_fields(
            cache_dir=Path("/cache"), commit_hash="abc1234", arch="arm64", config_flavor="rt"))
        self.assertEqual(ctx.artifacts_dir, Path("/cache/build_artifacts/abc1234/arm64/rt"))


class TestFastModeContext(unittest.TestCase):
    def test_inherits_common_fields_and_adds_fast_only_fields(self):
        ctx = FastModeContext(
            **_common_fields(),
            kernel_image_name="bzImage",
            build_image_name="bzImage",
            linux_arch="x86_64",
            boot_arch="x86",
            cross_compile="",
            target_arch_platform="linux/amd64",
            host_arch_platform="linux/amd64",
            container_image="registry.suse.com/bci/bci-base:latest",
            cc="gcc",
            host_cc="gcc",
            enable_configs=["CONFIG_VIRTIO_PCI"],
            disable_configs=["CONFIG_FOO"],
        )
        self.assertEqual(ctx.arch, "x86_64")  # inherited common field
        self.assertEqual(ctx.kernel_image_name, "bzImage")
        self.assertEqual(ctx.enable_configs, ["CONFIG_VIRTIO_PCI"])
        self.assertEqual(ctx.disable_configs, ["CONFIG_FOO"])
        self.assertIsInstance(ctx, PipelineContext)

    def test_defaults_apply_when_fast_only_fields_omitted(self):
        ctx = FastModeContext(**_common_fields())
        self.assertEqual(ctx.kernel_image_name, "")
        self.assertEqual(ctx.enable_configs, [])
        self.assertEqual(ctx.disable_configs, [])

    def test_mutable_default_lists_are_independent_between_instances(self):
        """make sure, no shared single mutable list across instances"""
        ctx1 = FastModeContext(**_common_fields())
        ctx2 = FastModeContext(**_common_fields())
        ctx1.enable_configs.append("CONFIG_ONLY_ON_CTX1")
        self.assertEqual(ctx2.enable_configs, [])

    def test_does_not_have_rpm_only_fields(self):
        ctx = FastModeContext(**_common_fields())
        with self.assertRaises(AttributeError):
            ctx.rpm_arch


class TestRpmModeContext(unittest.TestCase):
    def test_inherits_common_fields_and_adds_rpm_only_fields(self):
        ctx = RpmModeContext(
            **_common_fields(mode="rpm"),
            ibs_project="SUSE:SLFO:Main",
            obs_project="openSUSE:Factory",
            rpm_arch="x86_64",
            rpm_build_root=Path("/custom/build-root"),
        )
        self.assertEqual(ctx.mode, "rpm")  # common field
        self.assertEqual(ctx.ibs_project, "SUSE:SLFO:Main")
        self.assertEqual(ctx.rpm_build_root, Path("/custom/build-root"))
        self.assertIsInstance(ctx, PipelineContext)

    def test_default_rpm_build_root(self):
        ctx = RpmModeContext(**_common_fields(mode="rpm"))
        self.assertEqual(ctx.rpm_build_root, Path("/var/tmp/build-root"))

    def test_does_not_have_fast_only_fields(self):
        ctx = RpmModeContext(**_common_fields(mode="rpm"))
        with self.assertRaises(AttributeError):
            ctx.kernel_image_name
