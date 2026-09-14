import platform
import yaml
from pathlib import Path
from libs.console import get_logger
from libs.errors import KernelSandboxError
from libs.kernel_source_git import Repository

logger = get_logger(__name__)

DEFAULT_IBS_API_URL = "https://api.suse.de"
DEFAULT_OBS_API_URL = "https://api.opensuse.org"


class ConfigurationError(KernelSandboxError):
    pass


def get_host_arch():
    """Returns the host architecture."""
    arch = platform.machine()
    return arch if arch != "aarch64" else "arm64"


class ConfigManager:
    def __init__(self, yaml_path, workspace_path=None):
        self.yaml_path = Path(yaml_path)
        self.yaml_data = self._load_yaml()
        self.workspace = Path(workspace_path) if workspace_path is not None else None
        if self.workspace is not None:
            self.repo = Repository(self.workspace)
            self.parsed_vars = self.repo.parse_config_sh("HEAD")
        else:
            self.repo = None
            self.parsed_vars = {}

    def _load_yaml(self):
        if not self.yaml_path.exists():
            return {}
        with open(self.yaml_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def get_arch_profile(self, arch):
        """returns architecture_profiles from yaml."""
        profiles = self.yaml_data.get("architecture_profiles", {})
        if arch not in profiles:
            raise ConfigurationError(f"Architecture '{arch}' not defined in kernel_sandbox_profiles.yaml")
        return profiles[arch]

    def get_container_image(self):
        """returns container registry URI based on OBS/IBS targets parsed from rpm/config.sh"""
        if self.workspace is None:
            raise ConfigurationError(
                "get_container_image() requires a workspace to parse rpm/config.sh from, "
                "but this ConfigManager was constructed with yaml_path only"
            )
        ibs_project = self.parsed_vars.get("IBS_PROJECT", "")
        obs_project = self.parsed_vars.get("OBS_PROJECT", "")
        registries_config = self.yaml_data.get("container_registries", {})

        for target_project in [ibs_project, obs_project]:
            if not target_project:
                continue
            # prefer the most specific (longest) matching pattern
            # (ex. "SUSE:SLE-15-SP6" and "SUSE:SLE-15-SP6:Update").
            for pattern in registries_config:
                if target_project == pattern:
                    return registries_config[pattern]

        raise ConfigurationError(
            f"No container mapping exists for target project properties.\n"
            f"Parsed contexts -> IBS_PROJECT: '{ibs_project}', OBS_PROJECT: '{obs_project}'\n"
            f"Please add a directive rule inside kernel_sandbox_profiles.yaml and retry"
        )

    def _get_required_profile_key(self, arch, key):
        """Returns arch_profile[key], raising ConfigurationError if `key` is absent from the yaml profile."""
        arch_profile = self.get_arch_profile(arch)
        if key not in arch_profile:
            raise ConfigurationError(f"'{key}' definition missing in yaml profile for {arch}")
        return arch_profile[key]

    def get_container_platform(self, arch):
        """Returns the specific container platform string"""
        return self._get_required_profile_key(arch, "container_platform")

    def get_compiler_env(self, arch):
        """
        Determines the host compiler and cross-compiler prefix based on the yaml architecture profile.
        """
        cross_compile_prefix = self._get_required_profile_key(arch, "cross_compile")

        host_cc = "gcc"
        cross_compile = cross_compile_prefix if arch != get_host_arch() else ""
        logger.debug(f"Using host compiler: {host_cc}, cross-compiler prefix: {cross_compile}")
        cc = f"{cross_compile}gcc"
        return cc, cross_compile, host_cc

    def get_boot_arch(self, arch):
        """Returns the arch/<boot_arch>/boot/ directory name from yaml."""
        return self._get_required_profile_key(arch, "boot_arch")

    def get_kernel_image_name(self, arch):
        """Returns the specific compiled kernel binary filename from yaml."""
        return self._get_required_profile_key(arch, "kernel_image_name")

    def get_build_image_name(self, arch):
        """Returns the specific compiled kernel build image filename from yaml."""
        return self._get_required_profile_key(arch, "build_image_name")

    def get_kernel_path(self, arch, build_root):
        if self.workspace is None:
            raise ConfigurationError(
                "get_kernel_path() requires a workspace to parse rpm/config.sh from, "
                "but this ConfigManager was constructed with yaml_path only"
            )
        boot_arch = self.get_boot_arch(arch)
        kernel_filename = self.get_build_image_name(arch)

        if "SRCVERSION" not in self.parsed_vars:
            raise ConfigurationError("SRCVERSION definition missing in rpm/config.sh")

        version = self.parsed_vars["SRCVERSION"]
        return Path(build_root) / f"linux-{version}" / "arch" / boot_arch / "boot" / kernel_filename

    def get_osc_api_urls(self):
        """Returns (ibs_api_url, obs_api_url) for `osc -A <url>`"""
        configured = self.yaml_data.get("osc_api_urls", {})

        ibs_url = configured.get("ibs")
        if not ibs_url:
            logger.warning(f"osc_api_urls.ibs not set in kernel_sandbox_profiles.yaml, using default: {DEFAULT_IBS_API_URL}")
            ibs_url = DEFAULT_IBS_API_URL

        obs_url = configured.get("obs")
        if not obs_url:
            logger.warning(f"osc_api_urls.obs not set in kernel_sandbox_profiles.yaml, using default: {DEFAULT_OBS_API_URL}")
            obs_url = DEFAULT_OBS_API_URL

        return ibs_url, obs_url

    def get_qemu_profile(self, arch):
        """Returns the QEMU machine/cpu/console/qemu_bin profile dict for `arch`"""
        profiles = self.yaml_data.get("qemu_arch_profiles", {})
        if arch not in profiles:
            raise ConfigurationError(
                f"qemu_arch_profiles is missing from kernel_sandbox_profiles.yaml (no specific entry for '{arch}')"
            )

        profile = profiles[arch]
        for key in ("qemu_bin", "machine", "cpu_kvm", "cpu_tcg", "console"):
            if not profile.get(key):
                raise ConfigurationError(
                    f"qemu_arch_profiles.{arch}.{key} is missing or empty in kernel_sandbox_profiles.yaml"
                )
        return profile

    def get_kernel_config_patches(self):
        """
        Returns a tuple of (enable_kconfig, disable_kconfig) for kernel configs.
        """
        kconfig = self.yaml_data.get("kernel_config", {})
        enable_kconfig = kconfig.get("enable") or []
        disable_kconfig = kconfig.get("disable") or []
        return enable_kconfig, disable_kconfig
