import tempfile
import unittest
from pathlib import Path
from libs.image_customizer import (
    DependencyError,
    ImageCustomizationError,
    extract_kernel_version_from_rpm,
    install_rpms_to_image,
)


def mock_binary(directory, name, script_body):
    path = Path(directory) / name
    path.write_text(f"#!/bin/sh\n{script_body}\n")
    path.chmod(0o755)
    return str(path)


class TestExtractKernelVersionFromRpm(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmpdir.cleanup()

    def _mock_rpm(self, script_body):
        return mock_binary(self.tmpdir.name, "rpm", script_body)

    def test_uses_real_rpm_query_when_available(self):
        mock_rpm = self._mock_rpm("echo '6.12.0-0.g12345'")
        version = extract_kernel_version_from_rpm(Path("/mock/kernel-default-anything.rpm"), "default", rpm_bin=mock_rpm)
        self.assertEqual(version, "6.12.0-0.g12345")

    def test_falls_back_to_filename_parsing_when_rpm_query_fails(self):
        mock_rpm = self._mock_rpm("exit 1")
        rpm_path = Path("/mock/kernel-azure-6.12.0-rc1.x86_64.rpm")
        with self.assertLogs("kernel_sandbox", level="WARNING") as log_ctx:
            version = extract_kernel_version_from_rpm(rpm_path, "azure", rpm_bin=mock_rpm)
        self.assertEqual(version, "6.12.0-rc1.x86_64")
        self.assertTrue(any("falling back to filename parsing" in msg for msg in log_ctx.output))

    def test_falls_back_when_rpm_binary_is_missing(self):
        rpm_path = Path("/mock/kernel-azure-6.12.0-rc1.x86_64.rpm")
        with self.assertLogs("kernel_sandbox", level="WARNING") as log_ctx:
            version = extract_kernel_version_from_rpm(rpm_path, "azure", rpm_bin="/does-not-exist/rpm")
        self.assertEqual(version, "6.12.0-rc1.x86_64")
        self.assertTrue(any("falling back to filename parsing" in msg for msg in log_ctx.output))

    def test_fallback_returns_none_when_filename_does_not_match_flavor_prefix(self):
        """filename doesn't start with the expected flavor prefix."""
        mock_rpm = self._mock_rpm("exit 1")
        rpm_path = Path("/mock/some-other-package-1.0.rpm")
        self.assertIsNone(extract_kernel_version_from_rpm(rpm_path, "azure", rpm_bin=mock_rpm))

    def test_fallback_returns_none_when_missing_rpm_suffix(self):
        """matches the prefix but the file lacks a .rpm suffix."""
        mock_rpm = self._mock_rpm("exit 1")
        rpm_path = Path("/mock/kernel-default-6.12.0.notrpm")
        self.assertIsNone(extract_kernel_version_from_rpm(rpm_path, "default", rpm_bin=mock_rpm))


class TestInstallRpmsToImage(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.tmp_dir.name)
        self.image_path = self.workspace / "sandbox.qcow2"

    def tearDown(self):
        self.tmp_dir.cleanup()

    def _mock_tools(self, virt_customize_script_body, rpm_script_body="echo '6.12.0-0.g1234567'"):
        return {
            "virt_customize_bin": mock_binary(self.tmp_dir.name, "virt-customize", virt_customize_script_body),
            "rpm_bin": mock_binary(self.tmp_dir.name, "rpm", rpm_script_body),
        }

    def _make_rpm_cache(self, commit_hash="1234567abcdef", flavor="default", arch="x86_64"):
        rpm_cache_dir = self.workspace / "rpms"
        rpm_cache_dir.mkdir()
        rpm_file = rpm_cache_dir / f"kernel-{flavor}-6.12.0-0.g{commit_hash[:7]}.{arch}.rpm"
        rpm_file.touch()
        return rpm_cache_dir

    def test_missing_rpm_cache_dir_raises(self):
        rpm_cache_dir = self.workspace / "does-not-exist"
        with self.assertRaises(ImageCustomizationError) as ctx:
            install_rpms_to_image(self.image_path, "default", "1234567abcdef", "x86_64", rpm_cache_dir)
        self.assertEqual(f"RPM cache directory does not exist at {rpm_cache_dir}", str(ctx.exception))

    def test_no_matching_rpms_raises(self):
        rpm_cache_dir = self.workspace / "rpms"
        rpm_cache_dir.mkdir()
        with self.assertRaises(ImageCustomizationError) as ctx:
            install_rpms_to_image(self.image_path, "default", "1234567abcdef", "x86_64", rpm_cache_dir)
        self.assertEqual(f"No RPM files found in {rpm_cache_dir}", str(ctx.exception))

    def test_missing_virt_customize_raises_dependency_error(self):
        rpm_cache_dir = self._make_rpm_cache()
        mock_rpm = mock_binary(self.tmp_dir.name, "rpm", "echo '6.12.0-0.g1234567'")

        with self.assertRaises(DependencyError) as ctx:
            install_rpms_to_image(
                self.image_path, "default", "1234567abcdef", "x86_64", rpm_cache_dir,
                virt_customize_bin="/does-not-exist/virt-customize", rpm_bin=mock_rpm)
        self.assertEqual(
            "/does-not-exist/virt-customize not found - required for RPM mode. "
            "Install with: zypper in guestfs-tools",
            str(ctx.exception)
        )

    def test_missing_rpm_binary_raises_dependency_error(self):
        rpm_cache_dir = self._make_rpm_cache()
        with self.assertRaises(DependencyError) as ctx:
            install_rpms_to_image(
                self.image_path, "default", "1234567abcdef", "x86_64", rpm_cache_dir,
                virt_customize_bin=mock_binary(self.tmp_dir.name, "virt-customize", "exit 0"),
                rpm_bin="/does-not-exist/rpm")
        self.assertEqual(
            "/does-not-exist/rpm not found - required for RPM mode. "
            "Install with: zypper in rpm",
            str(ctx.exception)
        )

    def test_kernel_version_undetectable_raises(self):
        rpm_cache_dir = self.workspace / "rpms"
        rpm_cache_dir.mkdir()
        (rpm_cache_dir / "kernel-default_g1234567.x86_64.rpm").touch()
        tools = self._mock_tools("exit 0", rpm_script_body="exit 1")

        with self.assertRaises(ImageCustomizationError) as ctx:
            install_rpms_to_image(self.image_path, "default", "1234567abcdef", "x86_64", rpm_cache_dir, **tools)
        self.assertEqual("Could not detect kernel version from RPMs for flavor 'default'", str(ctx.exception))

    def test_success_runs_real_mock_virt_customize(self):
        rpm_cache_dir = self._make_rpm_cache()
        tools = self._mock_tools("exit 0")
        install_rpms_to_image(self.image_path, "default", "1234567abcdef", "x86_64", rpm_cache_dir, **tools)

    def test_virt_customize_failure_raises_with_real_stderr(self):
        rpm_cache_dir = self._make_rpm_cache()
        tools = self._mock_tools("echo 'guestfs: disk image corrupted' >&2; exit 1")
        with self.assertRaises(ImageCustomizationError) as ctx:
            install_rpms_to_image(self.image_path, "default", "1234567abcdef", "x86_64", rpm_cache_dir, **tools)
        self.assertIn("virt-customize failed: guestfs: disk image corrupted", str(ctx.exception))

    def test_virt_customize_timeout_raises(self):
        """a wedged virt-customize/libguestfs appliance must not hang the CLI forever."""
        rpm_cache_dir = self._make_rpm_cache()
        tools = self._mock_tools("sleep 5")
        with self.assertRaises(ImageCustomizationError) as ctx:
            install_rpms_to_image(
                self.image_path, "default", "1234567abcdef", "x86_64", rpm_cache_dir, timeout=0.3, **tools)
        self.assertIn("virt-customize timed out after 0.3s", str(ctx.exception))
