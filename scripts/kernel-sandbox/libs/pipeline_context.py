"""
Contexts passed to BuildEngine / ImagePreparer / BootEngine
"""
from pathlib import Path


class PipelineContext:
    """Fields required regardless of mode."""
    def __init__(
            self, workspace, build_root, cache_dir, commit_hash, arch, config_flavor, mode,
            refresh_cache, use_busybox_initrd, qemu_bin, extra_qemu, host_arch, ssh_enabled, qemu_profile=None):
        self.workspace = workspace
        self.build_root = build_root
        self.cache_dir = cache_dir
        self.commit_hash = commit_hash
        self.arch = arch
        self.config_flavor = config_flavor
        self.mode = mode
        self.refresh_cache = refresh_cache
        self.use_busybox_initrd = use_busybox_initrd
        self.qemu_bin = qemu_bin
        self.extra_qemu = extra_qemu
        self.host_arch = host_arch
        self.ssh_enabled = ssh_enabled
        self.qemu_profile = qemu_profile

    @property
    def artifacts_dir(self):
        """cache layout, shared by all three engines."""
        return Path(self.cache_dir) / "build_artifacts" / self.commit_hash / self.arch / self.config_flavor


class FastModeContext(PipelineContext):
    """Additional fields only meaningful when mode == 'fast'."""
    def __init__(
            self, kernel_image_name="", build_image_name="", linux_arch="", boot_arch="",
            cross_compile="", target_arch_platform="", host_arch_platform="", container_image="",
            cc="", host_cc="", enable_configs=None, disable_configs=None, **common_fields):
        super().__init__(**common_fields)
        self.kernel_image_name = kernel_image_name
        self.build_image_name = build_image_name
        self.linux_arch = linux_arch
        self.boot_arch = boot_arch
        self.cross_compile = cross_compile
        self.target_arch_platform = target_arch_platform
        self.host_arch_platform = host_arch_platform
        self.container_image = container_image
        self.cc = cc
        self.host_cc = host_cc
        self.enable_configs = enable_configs if enable_configs is not None else []
        self.disable_configs = disable_configs if disable_configs is not None else []


class RpmModeContext(PipelineContext):
    """Additional fields only meaningful when mode == 'rpm'."""
    def __init__(
            self, ibs_project=None, obs_project=None, ibs_api_url="", obs_api_url="", rpm_arch="", cow_image=None,
            rpm_build_root=Path("/var/tmp/build-root"), **common_fields):
        super().__init__(**common_fields)
        self.ibs_project = ibs_project
        self.obs_project = obs_project
        self.ibs_api_url = ibs_api_url
        self.obs_api_url = obs_api_url
        self.rpm_arch = rpm_arch
        self.cow_image = cow_image
        self.rpm_build_root = rpm_build_root
