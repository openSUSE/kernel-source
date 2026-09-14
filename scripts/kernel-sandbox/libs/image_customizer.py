"""
QCOW2 image customization utils - installs freshly built kernel RPMs into a
base qcow2 image via virt-customize.
"""
import shutil
import subprocess
import tempfile
from pathlib import Path
from libs.console import get_logger
from libs.errors import KernelSandboxError

logger = get_logger(__name__)
DEFAULT_VIRT_CUSTOMIZE_TIMEOUT = 900


class DependencyError(KernelSandboxError):
    pass


class ImageCustomizationError(KernelSandboxError):
    pass


def install_rpms_to_image(
        image_path, config_flavor, commit_hash, rpm_arch, rpm_cache_dir,
        virt_customize_bin="virt-customize", rpm_bin="rpm", timeout=DEFAULT_VIRT_CUSTOMIZE_TIMEOUT):
    """
    Install RPMs into a qcow2 image using virt-customize with advanced chained run-commands

    This function performs:
    1. Upload and install kernel RPMs with --force --oldpackage
    2. Run dracut --force --no-hostonly --kver <version>-<flavor>
    3. Regenerate grub config
    4. Disable jeos-firstboot services
    5. Configure autologin for serial console (ttyS0)

    For the equivalent manual, step-by-step shell sequence (useful when
    debugging a failure here), see "Reproducing --mode rpm's image-customization
    step by hand" in README-execute.kernel-sandbox.md.
    """
    rpm_cache_dir = Path(rpm_cache_dir)
    if not rpm_cache_dir.exists():
        raise ImageCustomizationError(f"RPM cache directory does not exist at {rpm_cache_dir.resolve()}")

    rpm_files = list(rpm_cache_dir.glob(f"kernel-{config_flavor}*g{commit_hash[:7]}.{rpm_arch}.rpm"))
    if not rpm_files:
        raise ImageCustomizationError(f"No RPM files found in {rpm_cache_dir.resolve()}")

    logger.info(f"Found {len(rpm_files)} RPM(s) to install into sandbox image")

    if not shutil.which(rpm_bin):
        raise DependencyError(f"{rpm_bin} not found - required for RPM mode. Install with: zypper in rpm")

    # Extract kernel version from the first matching kernel flavor RPM
    kernel_version = None
    for rpm in rpm_files:
        if f"kernel-{config_flavor}" in rpm.name:
            kernel_version = extract_kernel_version_from_rpm(rpm, config_flavor, rpm_bin=rpm_bin)
            if kernel_version:
                logger.info(f"Detected kernel version: {kernel_version} ({config_flavor})")
                break

    if not kernel_version:
        raise ImageCustomizationError(f"Could not detect kernel version from RPMs for flavor '{config_flavor}'")

    if not shutil.which(virt_customize_bin):
        raise DependencyError(f"{virt_customize_bin} not found - required for RPM mode. Install with: zypper in guestfs-tools")

    logger.info("[BUILD] Using virt-customize to inject RPMs and configure image...")
    qcow2_setup_src = Path(__file__).resolve().parent.parent / "assets" / "qcow2_setup.tmpl"
    if not qcow2_setup_src.exists():
        raise ImageCustomizationError(f"QCOW2 setup template missing at {qcow2_setup_src}")

    setup_script_content = qcow2_setup_src.read_text(encoding="utf-8", errors="ignore")
    setup_script_content = setup_script_content.replace("{{KERNEL_VERSION}}", kernel_version)
    setup_script_content = setup_script_content.replace("{{CONFIG_FLAVOR}}", config_flavor)
    rpm_names_str = " ".join(f"/root/{rpm.name}" for rpm in rpm_files if rpm.name.startswith(f"kernel-{config_flavor}-{kernel_version}"))
    setup_script_content = setup_script_content.replace("{{RPM_NAMES}}", rpm_names_str)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".sh", delete=False) as temp_script:
        temp_script.write(setup_script_content)
        temp_script_path = temp_script.name

    try:
        cmd = [virt_customize_bin, "-a", str(image_path)]
        # upload all target RPMs
        for rpm in rpm_files:
            cmd.extend(["--upload", f"{rpm}:/root/{rpm.name}"])
        # upload the compiled template execution script
        cmd.extend(["--upload", f"{temp_script_path}:/root/qcow2_setup.sh"])
        # execute the script inside the guest container environment
        cmd.extend(["--run-command", "chmod +x /root/qcow2_setup.sh"])
        cmd.extend(["--run-command", "/root/qcow2_setup.sh"])

        # Execute the chained command
        logger.info("[BUILD] Executing image customization (this may take a few minutes)...")
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired as e:
            stderr = e.stderr.strip() if e.stderr else ""
            raise ImageCustomizationError(
                f"virt-customize timed out after {timeout}s"
                + (f"\nPartial stderr: {stderr}" if stderr else "")
            )
        if res.returncode != 0:
            raise ImageCustomizationError(f"virt-customize failed: {res.stderr.strip()}")
        logger.info(f"virt-customize output: {res.stdout}")
        logger.info("Image customization completed successfully")
    finally:
        Path(temp_script_path).unlink(missing_ok=True)


def extract_kernel_version_from_rpm(rpm_path, config_flavor, rpm_bin="rpm"):
    """Extract kernel version from RPM filename or query"""
    try:
        # get version (kver)
        result = subprocess.run(
            [rpm_bin, "-q", "--qf", "%{VERSION}-%{RELEASE}\\n", "-p", str(rpm_path)],
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, OSError) as e:
        logger.warning(f"'{rpm_bin} -q' failed ({e}); falling back to filename parsing for {rpm_path.name}")
        # Fallback: parse from filename dynamically based on config_flavor,
        # ex: "kernel-azure-6.12.0-rc1.x86_64.rpm" -> "6.12.0-rc1.x86_64"
        prefix = f"kernel-{config_flavor}-"
        suffix = ".rpm"
        name = rpm_path.name
        if name.startswith(prefix) and name.endswith(suffix):
            return name[len(prefix):-len(suffix)]
        return None
