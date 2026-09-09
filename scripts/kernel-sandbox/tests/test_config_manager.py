import platform
import pygit2
import tempfile
import unittest
import yaml
from pathlib import Path
from libs.config_manager import DEFAULT_IBS_API_URL, DEFAULT_OBS_API_URL, ConfigManager, ConfigurationError, get_host_arch


def TestRepoSetup(workspace_path, config_content):
    repo = pygit2.init_repository(str(workspace_path), bare=False)
    sig = pygit2.Signature("testuser", "testuser@suse.de")
    root_tb = repo.TreeBuilder()
    config_blob_oid = repo.create_blob(config_content.encode("utf-8"))
    rpm_tb = repo.TreeBuilder()
    rpm_tb.insert("config.sh", config_blob_oid, pygit2.GIT_FILEMODE_BLOB)
    root_tb.insert("rpm", rpm_tb.write(), pygit2.GIT_FILEMODE_TREE)
    repo.create_commit("refs/heads/master", sig, sig, "config.sh commit", root_tb.write(), [])
    repo.set_head("refs/heads/master")
    return repo


class TestGetHostArch(unittest.TestCase):
    def setUp(self):
        self.original_machine = platform.machine

    def tearDown(self):
        platform.machine = self.original_machine

    def test_normalizes_aarch64_to_arm64(self):
        platform.machine = lambda: "aarch64"
        self.assertEqual(get_host_arch(), "arm64")

    def test_passes_through_other_arches_unchanged(self):
        platform.machine = lambda: "x86_64"
        self.assertEqual(get_host_arch(), "x86_64")


class TestConfigManager(unittest.TestCase):
    def setUp(self):
        tmp_dir_ctx = tempfile.TemporaryDirectory()
        self.addCleanup(tmp_dir_ctx.cleanup)
        self.tmp_dir = tmp_dir_ctx.name
        self.workspace_path = Path(self.tmp_dir) / "workspace"
        self.workspace_path.mkdir()
        self.yaml_path = Path(self.tmp_dir) / "kernel_sandbox_profiles.yaml"
        self.yaml_data = {
            "container_registries": {
                "SUSE:SLFO:Main": "registry.opensuse.org/kernel-build:16.1",
                "openSUSE:Factory": "registry.opensuse.org/kernel-build:factory",
            },
            "architecture_profiles": {
                "x86_64": {
                    "container_platform": "linux/amd64",
                    "linux_arch": "x86_64",
                    "boot_arch": "x86",
                    "rpm_arch": "x86_64",
                    "cross_compile": "x86_64-suse-linux-",
                    "kernel_image_name": "vmlinuz",
                    "build_image_name": "bzImage"
                },
                "arm64": {
                    "container_platform": "linux/arm64",
                    "linux_arch": "arm64",
                    "boot_arch": "arm64",
                    "rpm_arch": "aarch64",
                    "cross_compile": "aarch64-suse-linux-",
                    "kernel_image_name": "Image",
                    "build_image_name": "Image"
                }
            },
            "kernel_config": {
                "enable": ["CONFIG_VIRTIO_PCI"],
                "disable": ["CONFIG_FOO"],
            }
        }
        self.write_yaml(self.yaml_data)

    def write_yaml(self, data):
        with open(self.yaml_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f)

    def config_sh(self, ibs="SUSE:SLFO:Main", obs="openSUSE:Factory", srcversion="6.12"):
        return f"SRCVERSION={srcversion}\nIBS_PROJECT={ibs}\nOBS_PROJECT={obs}\n"

    def test_initialization_and_yaml_load(self):
        TestRepoSetup(self.workspace_path, self.config_sh())
        manager = ConfigManager(self.yaml_path, self.workspace_path)
        self.assertEqual(manager.parsed_vars["SRCVERSION"], "6.12")
        self.assertIn("x86_64", manager.yaml_data["architecture_profiles"])

    def test_missing_yaml_file_defaults_to_empty_dict(self):
        TestRepoSetup(self.workspace_path, self.config_sh())
        manager = ConfigManager(Path(self.tmp_dir) / "missing.yaml", self.workspace_path)
        self.assertEqual(manager.yaml_data, {})

    def test_workspace_optional_yaml_only_methods_still_work(self):
        """purely yaml-backed methods must work without a workspace/git repo"""
        manager = ConfigManager(yaml_path=self.yaml_path)
        self.assertIsNone(manager.repo)
        self.assertEqual(manager.parsed_vars, {})
        self.assertEqual(manager.get_arch_profile("x86_64")["boot_arch"], "x86")
        cc, _, _ = manager.get_compiler_env("x86_64")
        self.assertEqual(cc, "gcc")

    def test_workspace_optional_git_backed_methods_raise_clearly(self):
        """get_container_image()/get_kernel_path() need rpm/config.sh,
        which needs a workspace"""
        manager = ConfigManager(yaml_path=self.yaml_path)
        with self.assertRaises(ConfigurationError) as ctx:
            manager.get_container_image()
        self.assertEqual(
            "get_container_image() requires a workspace to parse rpm/config.sh "
            "from, but this ConfigManager was constructed with yaml_path only",
            str(ctx.exception),
        )

        with self.assertRaises(ConfigurationError) as ctx:
            manager.get_kernel_path("x86_64", Path("/mock/build"))
        self.assertEqual(
            "get_kernel_path() requires a workspace to parse rpm/config.sh "
            "from, but this ConfigManager was constructed with yaml_path only",
            str(ctx.exception),
        )

    def test_get_arch_profile(self):
        TestRepoSetup(self.workspace_path, self.config_sh())
        manager = ConfigManager(self.yaml_path, self.workspace_path)
        self.assertEqual(manager.get_arch_profile("x86_64")["boot_arch"], "x86")

        with self.assertRaises(ConfigurationError) as ctx:
            manager.get_arch_profile("riscv64")
        self.assertIn("Architecture 'riscv64' not defined", str(ctx.exception))

    def test_get_container_image_matches_ibs(self):
        TestRepoSetup(self.workspace_path, self.config_sh(ibs="SUSE:SLFO:Main", obs="openSUSE:Factory"))
        manager = ConfigManager(self.yaml_path, self.workspace_path)
        self.assertEqual(manager.get_container_image(), "registry.opensuse.org/kernel-build:16.1")

    def test_get_container_image_falls_back_to_obs(self):
        TestRepoSetup(self.workspace_path, self.config_sh(ibs="SUSE:UNKNOWN", obs="openSUSE:Factory"))
        manager = ConfigManager(self.yaml_path, self.workspace_path)
        self.assertEqual(manager.get_container_image(), "registry.opensuse.org/kernel-build:factory")

    def test_get_container_image_no_match_raises(self):
        TestRepoSetup(self.workspace_path, self.config_sh(ibs="SUSE:UNKNOWN", obs="UNKNOWN:PROJECT"))
        manager = ConfigManager(self.yaml_path, self.workspace_path)
        with self.assertRaises(ConfigurationError) as ctx:
            manager.get_container_image()
        self.assertIn("No container mapping exists", str(ctx.exception))

    def test_get_container_image_prefers_exact_pattern_match(self):
        """target_project == pattern"""
        yaml_data = dict(self.yaml_data)
        yaml_data["container_registries"] = {
            "SUSE:SLE-15-SP6": "registry.opensuse.org/kernel-build:15-sp6",
            "SUSE:SLE-15-SP6:Update": "registry.opensuse.org/kernel-build:15-sp6-update",
        }
        self.write_yaml(yaml_data)
        TestRepoSetup(self.workspace_path, self.config_sh(ibs="SUSE:SLE-15-SP6:Update", obs=""))
        manager = ConfigManager(self.yaml_path, self.workspace_path)
        self.assertEqual(manager.get_container_image(), "registry.opensuse.org/kernel-build:15-sp6-update")

    def test_get_compiler_env(self):
        TestRepoSetup(self.workspace_path, self.config_sh())
        manager = ConfigManager(self.yaml_path, self.workspace_path)

        cc, cross, host_cc = manager.get_compiler_env("x86_64")
        self.assertEqual(cc, "gcc")
        self.assertEqual(cross, "")
        self.assertEqual(host_cc, "gcc")

        cc, cross, host_cc = manager.get_compiler_env("arm64")
        self.assertEqual(cc, "aarch64-suse-linux-gcc")
        self.assertEqual(cross, "aarch64-suse-linux-")
        self.assertEqual(host_cc, "gcc")

    def test_get_compiler_env_missing_cross_compile_raises(self):
        yaml_data = dict(self.yaml_data)
        yaml_data["architecture_profiles"] = {"x86_64": {"boot_arch": "x86"}}
        self.write_yaml(yaml_data)
        TestRepoSetup(self.workspace_path, self.config_sh())
        manager = ConfigManager(self.yaml_path, self.workspace_path)
        with self.assertRaises(ConfigurationError) as ctx:
            manager.get_compiler_env("x86_64")
        self.assertEqual("'cross_compile' definition missing in yaml profile for x86_64", str(ctx.exception))

    def test_get_container_platform_missing_key_raises(self):
        yaml_data = dict(self.yaml_data)
        yaml_data["architecture_profiles"] = {"x86_64": {"boot_arch": "x86"}}
        self.write_yaml(yaml_data)
        TestRepoSetup(self.workspace_path, self.config_sh())
        manager = ConfigManager(self.yaml_path, self.workspace_path)
        with self.assertRaises(ConfigurationError) as ctx:
            manager.get_container_platform("x86_64")
        self.assertEqual("'container_platform' definition missing in yaml profile for x86_64", str(ctx.exception))

    def test_get_kernel_path(self):
        TestRepoSetup(self.workspace_path, self.config_sh(srcversion="6.12"))
        manager = ConfigManager(self.yaml_path, self.workspace_path)
        build_root = Path("/mock/build")

        self.assertEqual(str(manager.get_kernel_path("x86_64", build_root)), "/mock/build/linux-6.12/arch/x86/boot/bzImage")
        self.assertEqual(str(manager.get_kernel_path("arm64", build_root)), "/mock/build/linux-6.12/arch/arm64/boot/Image")

    def test_get_kernel_path_missing_srcversion_raises(self):
        TestRepoSetup(self.workspace_path, "IBS_PROJECT=SUSE:SLFO:Main\n")
        manager = ConfigManager(self.yaml_path, self.workspace_path)
        with self.assertRaises(ConfigurationError) as ctx:
            manager.get_kernel_path("x86_64", Path("/mock/build"))
        self.assertIn("SRCVERSION definition missing", str(ctx.exception))

    def test_get_qemu_profile_returns_arch_entry(self):
        yaml_data = dict(self.yaml_data)
        yaml_data["qemu_arch_profiles"] = {
            "s390x": {
                "qemu_bin": "qemu-system-s390x", "machine": "s390-ccw-virtio",
                "cpu_kvm": "host", "cpu_tcg": "max", "console": "ttysclp0"},
        }
        self.write_yaml(yaml_data)
        TestRepoSetup(self.workspace_path, self.config_sh())
        manager = ConfigManager(self.yaml_path, self.workspace_path)
        self.assertEqual(manager.get_qemu_profile("s390x")["machine"], "s390-ccw-virtio")

    def test_get_qemu_profile_raises_for_unlisted_arch(self):
        yaml_data = dict(self.yaml_data)
        yaml_data["qemu_arch_profiles"] = {
            "s390x": {
                "qemu_bin": "qemu-system-s390x", "machine": "s390-ccw-virtio",
                "cpu_kvm": "host", "cpu_tcg": "max", "console": "ttysclp0"},
        }
        self.write_yaml(yaml_data)
        TestRepoSetup(self.workspace_path, self.config_sh())
        manager = ConfigManager(self.yaml_path, self.workspace_path)
        with self.assertRaises(ConfigurationError) as ctx:
            manager.get_qemu_profile("riscv64")
        self.assertEqual(
            "qemu_arch_profiles is missing from kernel_sandbox_profiles.yaml (no specific entry for 'riscv64')",
            str(ctx.exception))

    def test_get_qemu_profile_raises_when_qemu_prfoiles_missing_entirely(self):
        TestRepoSetup(self.workspace_path, self.config_sh())
        manager = ConfigManager(self.yaml_path, self.workspace_path)
        with self.assertRaises(ConfigurationError) as ctx:
            manager.get_qemu_profile("riscv64")
        self.assertEqual(
            "qemu_arch_profiles is missing from kernel_sandbox_profiles.yaml (no specific entry for 'riscv64')",
            str(ctx.exception))

    def test_get_qemu_profile_raises_on_missing_key(self):
        yaml_data = dict(self.yaml_data)
        yaml_data["qemu_arch_profiles"] = {
            # cpu_tcg missing
            "s390x": {"qemu_bin": "qemu-system-s390x", "machine": "s390-ccw-virtio", "cpu_kvm": "host", "console": "ttysclp0"},
        }
        self.write_yaml(yaml_data)
        TestRepoSetup(self.workspace_path, self.config_sh())
        manager = ConfigManager(self.yaml_path, self.workspace_path)
        with self.assertRaises(ConfigurationError) as ctx:
            manager.get_qemu_profile("s390x")
        self.assertEqual("qemu_arch_profiles.s390x.cpu_tcg is missing or empty in kernel_sandbox_profiles.yaml", str(ctx.exception))

    def test_get_qemu_profile_raises_on_empty_value(self):
        yaml_data = dict(self.yaml_data)
        yaml_data["qemu_arch_profiles"] = {
            "s390x": {"qemu_bin": "qemu-system-s390x", "machine": "", "cpu_kvm": "host", "cpu_tcg": "max", "console": "ttysclp0"},
        }
        self.write_yaml(yaml_data)
        TestRepoSetup(self.workspace_path, self.config_sh())
        manager = ConfigManager(self.yaml_path, self.workspace_path)
        with self.assertRaises(ConfigurationError) as ctx:
            manager.get_qemu_profile("s390x")
        self.assertEqual("qemu_arch_profiles.s390x.machine is missing or empty in kernel_sandbox_profiles.yaml", str(ctx.exception))

    def test_get_qemu_profile_raises_when_qemu_bin_missing(self):
        yaml_data = dict(self.yaml_data)
        yaml_data["qemu_arch_profiles"] = {
            "s390x": {"machine": "s390-ccw-virtio", "cpu_kvm": "host", "cpu_tcg": "max", "console": "ttysclp0"},
        }
        self.write_yaml(yaml_data)
        TestRepoSetup(self.workspace_path, self.config_sh())
        manager = ConfigManager(self.yaml_path, self.workspace_path)
        with self.assertRaises(ConfigurationError) as ctx:
            manager.get_qemu_profile("s390x")
        self.assertEqual("qemu_arch_profiles.s390x.qemu_bin is missing or empty in kernel_sandbox_profiles.yaml", str(ctx.exception))

    def test_get_qemu_profile_includes_qemu_bin(self):
        yaml_data = dict(self.yaml_data)
        yaml_data["qemu_arch_profiles"] = {
            "s390x": {
                "qemu_bin": "qemu-system-s390x", "machine": "s390-ccw-virtio",
                "cpu_kvm": "host", "cpu_tcg": "max", "console": "ttysclp0"},
        }
        self.write_yaml(yaml_data)
        TestRepoSetup(self.workspace_path, self.config_sh())
        manager = ConfigManager(self.yaml_path, self.workspace_path)
        self.assertEqual(manager.get_qemu_profile("s390x")["qemu_bin"], "qemu-system-s390x")

    def test_get_kernel_config_patches(self):
        TestRepoSetup(self.workspace_path, self.config_sh())
        manager = ConfigManager(self.yaml_path, self.workspace_path)
        enable, disable = manager.get_kernel_config_patches()
        self.assertEqual(enable, ["CONFIG_VIRTIO_PCI"])
        self.assertEqual(disable, ["CONFIG_FOO"])

    def test_get_osc_api_urls_uses_configured_values(self):
        yaml_data = dict(self.yaml_data)
        yaml_data["osc_api_urls"] = {"ibs": "https://api.example-ibs.test", "obs": "https://api.example-obs.test"}
        self.write_yaml(yaml_data)
        TestRepoSetup(self.workspace_path, self.config_sh())
        manager = ConfigManager(self.yaml_path, self.workspace_path)

        ibs_url, obs_url = manager.get_osc_api_urls()
        self.assertEqual(ibs_url, "https://api.example-ibs.test")
        self.assertEqual(obs_url, "https://api.example-obs.test")

    def test_get_osc_api_urls_falls_back_to_defaults_with_warning_when_section_missing(self):
        TestRepoSetup(self.workspace_path, self.config_sh())
        manager = ConfigManager(self.yaml_path, self.workspace_path)

        with self.assertLogs("kernel_sandbox", level="WARNING") as log_ctx:
            ibs_url, obs_url = manager.get_osc_api_urls()
        self.assertEqual(ibs_url, DEFAULT_IBS_API_URL)
        self.assertEqual(obs_url, DEFAULT_OBS_API_URL)
        self.assertTrue(any("osc_api_urls.ibs not set" in msg for msg in log_ctx.output))
        self.assertTrue(any("osc_api_urls.obs not set" in msg for msg in log_ctx.output))

    def test_get_osc_api_urls_falls_back_per_key_when_partially_configured(self):
        yaml_data = dict(self.yaml_data)
        yaml_data["osc_api_urls"] = {"ibs": "https://api.example-ibs.test"}
        self.write_yaml(yaml_data)
        TestRepoSetup(self.workspace_path, self.config_sh())
        manager = ConfigManager(self.yaml_path, self.workspace_path)

        with self.assertLogs("kernel_sandbox", level="WARNING") as log_ctx:
            ibs_url, obs_url = manager.get_osc_api_urls()
        self.assertEqual(ibs_url, "https://api.example-ibs.test")
        self.assertEqual(obs_url, DEFAULT_OBS_API_URL)
        self.assertTrue(any("osc_api_urls.obs not set" in msg for msg in log_ctx.output))

    def test_get_kernel_config_patches_missing_section_returns_empty_lists(self):
        """no 'kernel_config' section in the YAML at all."""
        yaml_data = {k: v for k, v in self.yaml_data.items() if k != "kernel_config"}
        self.write_yaml(yaml_data)
        TestRepoSetup(self.workspace_path, self.config_sh())
        manager = ConfigManager(self.yaml_path, self.workspace_path)
        enable, disable = manager.get_kernel_config_patches()
        self.assertEqual(enable, [])
        self.assertEqual(disable, [])
