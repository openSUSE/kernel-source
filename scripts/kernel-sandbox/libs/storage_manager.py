import shutil
import subprocess
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from libs.console import get_logger
from libs.errors import KernelSandboxError

logger = get_logger(__name__)
DEFAULT_QCOW2_IMG_CREATE_TIMEOUT = 60


class DownloadError(KernelSandboxError):
    pass


class ImageNotFoundError(KernelSandboxError):
    pass


class Qcow2ImageError(KernelSandboxError):
    pass


class HTTPDownloader:
    def download_file(self, url, dest):
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        # Use a temporary file path to store it
        tmp_path = dest.with_suffix(dest.suffix + ".tmp")
        logger.info(f"Downloading {url} to {dest}...")
        try:
            if tmp_path.exists():
                tmp_path.unlink()

            # download to tmpfile and rename it
            with urllib.request.urlopen(url, timeout=60) as response, open(tmp_path, "wb") as out_file:
                shutil.copyfileobj(response, out_file)
            tmp_path.rename(dest)
            logger.info("Download complete.")
        except Exception as e:
            if tmp_path.exists():
                tmp_path.unlink()
            raise DownloadError(f"Download failed: {e}")


class JeosDirectUrlStrategy:
    """Handles an absolute, explicit direct file download path."""
    def __init__(self, config_data):
        self.direct_url = config_data["direct_url"]

    def get_download_url(self, arch):
        filename = self.direct_url.rsplit("/", 1)[-1]
        return self.direct_url, filename, False


class JeosBaseUrlStrategy:
    """Handles directory spidering paths."""
    def __init__(self, config_data):
        self.base_url = config_data["base_url"]

    def get_download_url(self, arch):
        url = self.base_url.rstrip("/") + "/"
        if f"/{arch}/" not in url:
            url = f"{url}{arch}/"
        # filename will be resolved by the download engine
        return url, None, True


class JeosFallbackStrategy:
    """fallback download URL"""
    def __init__(self, template_project):
        self.template_project = template_project

    def get_download_url(self, arch):
        url = f"https://download.opensuse.org/repositories/SUSE:/Templates:/Images:/{self.template_project}/images/"
        return url, None, True


class StrategyResolver:
    """Resolves config mapping_entries to concrete strategy interfaces."""
    def get_download_strategy(self, mapping_entry):
        if isinstance(mapping_entry, dict):
            if "direct_url" in mapping_entry:
                return JeosDirectUrlStrategy(mapping_entry)
            if "base_url" in mapping_entry:
                return JeosBaseUrlStrategy(mapping_entry)
        return JeosFallbackStrategy(mapping_entry)


class _Qcow2LinkExtractor(HTMLParser):
    """Collects href values ending in '.qcow2' from <a> tags in an HTML directory listing page"""
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag != "a":
            return
        for name, value in attrs:
            if name == "href" and value and value.endswith(".qcow2"):
                self.links.append(value)


def _extract_qcow2_links(html_text):
    parser = _Qcow2LinkExtractor()
    parser.feed(html_text)
    return parser.links


class ImageFinder:
    """
    Image discovery and download orchestrator.
    """
    def __init__(self, downloader=None, strategy_resolver=None, exclude_patterns=None):
        self.downloader = downloader or HTTPDownloader()
        self.strategy_resolver = strategy_resolver or StrategyResolver()
        self.exclude_patterns = exclude_patterns if exclude_patterns is not None else []

    def download_external_image(self, arch, mapping_entry, cache_dir, include_filters=None):
        """Download image from an external download server using resolved strategies."""
        image_cache_dir = Path(cache_dir) / "base-images"
        image_cache_dir.mkdir(parents=True, exist_ok=True)

        strategy = self.strategy_resolver.get_download_strategy(mapping_entry)
        target_url, chosen_file, requires_parsing = strategy.get_download_url(arch)

        if not requires_parsing:
            dest_path = image_cache_dir / chosen_file
            if dest_path.exists():
                logger.info(f"[CACHE HIT] Using cached direct download: {dest_path}")
                return dest_path
            logger.info(f"[DOWNLOAD] Executing explicit direct URL fetch for {chosen_file}...")
            self.downloader.download_file(target_url, dest_path)
            return dest_path

        logger.info(f"Attempting to download from {target_url}...")

        try:
            # Fetch the directory listing
            with urllib.request.urlopen(target_url, timeout=30) as response:
                html = response.read().decode("utf-8")

            qcow2_files = _extract_qcow2_links(html)

            # Filter for identifiers and architecture
            matching = []
            for fname in qcow2_files:
                fname_lower = fname.lower()

                # Apply custom inclusion filters if provided (ex: jeos/minimal-vm)
                if include_filters:
                    has_valid_type = any(filt in fname_lower for filt in include_filters)
                else:
                    has_valid_type = True

                if has_valid_type and arch in fname_lower:
                    # Exclude unwanted variants
                    if not any(x in fname_lower for x in self.exclude_patterns):
                        matching.append(fname)

            if not matching:
                raise ImageNotFoundError(f"No matching image found for architecture: {arch}")

            # Pick the highest build number (typically the latest)
            matching.sort(reverse=True)
            chosen_file = matching[0]

            download_url = target_url + chosen_file
            dest_path = image_cache_dir / chosen_file

            if dest_path.exists():
                logger.info(f"[CACHE HIT] Using cached download: {dest_path}")
                return dest_path

            logger.info(f"[DOWNLOAD] Downloading {chosen_file}...")
            self.downloader.download_file(download_url, dest_path)
            return dest_path

        except ImageNotFoundError:
            raise
        except Exception as e:
            raise DownloadError(f"Failed to download external image: {e}")

    def find_image(self, arch, target_version, cache_dir, local_search_path=None,
                   mapping_entry=None, include_filters=None, qcow_match_pattern="kvm",
                   fallback_hint=None):
        """
        to find the image.
        -> check cache path first.
        -> check external download via strategies.
        -> searche local search path (ex: IBS) if available (fallback).
        """
        image_cache_dir = Path(cache_dir) / "base-images"
        image_cache_dir.mkdir(parents=True, exist_ok=True)

        # Strategy 1: Check cache (with version enforcement)
        for p in sorted(image_cache_dir.glob("*.qcow2"), key=lambda x: x.stat().st_mtime, reverse=True):
            if (target_version and target_version in p.name) and arch in p.name.lower():
                logger.info(f"[CACHE HIT] Using cached image: {p}")
                return p

        # Strategy 2: External download
        if mapping_entry:
            logger.info(f"No local {target_version} image found, attempting external download...")
            try:
                return self.download_external_image(
                    arch=arch,
                    mapping_entry=mapping_entry,
                    cache_dir=cache_dir,
                    include_filters=include_filters
                )
            except Exception as e:
                logger.warning(f"External download pipeline encountered an issue: {e}")

        # Strategy 3: Local search path (ex: Internal IBS)(Fallback)
        if local_search_path:
            local_dir = Path(local_search_path)
            if local_dir.is_dir():
                logger.info(f"Local search path(IBS) is visible. Searching for {target_version} matches...")
                qcow2_files = []

                for p in local_dir.rglob("*.qcow2"):
                    root_lower = str(p.parent).lower()
                    file_lower = p.name.lower()

                    # Enforce version match
                    if target_version and target_version not in str(p.parent):
                        continue

                    # Exclude unwanted variants
                    if any(x in root_lower or x in file_lower for x in self.exclude_patterns):
                        continue

                    if not qcow_match_pattern or qcow_match_pattern in file_lower:
                        qcow2_files.append(p)

                # Sort by modification time, newest first
                qcow2_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)

                for p in qcow2_files:
                    if arch in p.name.lower():
                        logger.info(f"Found exact local version match: {p}")
                        return p
            else:
                logger.info("Local search path (IBS) mount point is not active or accessible.")

        error_msg = f"Failed to acquire valid target image '{target_version}' from cache, mirror sites, or local file trees."
        logger.error(error_msg)
        if fallback_hint:
            logger.info(f"Fallback: {fallback_hint}")
        raise ImageNotFoundError(error_msg)


class Qcow2Manager:
    """Disk image creation and virtualization with qemu utils wrapper."""

    @staticmethod
    def build_create_cow_image_command(base_image_path, target_path):
        return [
            "qemu-img", "create",
            "-f", "qcow2",
            "-F", "qcow2",
            "-b", Path(base_image_path).resolve(),
            Path(target_path)
        ]

    @staticmethod
    def create_cow_image(base_image_path, target_path, timeout=DEFAULT_QCOW2_IMG_CREATE_TIMEOUT):
        """Creates a copy-on-write image using qemu-img."""
        logger.info(f"Creating copy-on-write image '{target_path}' with backing file '{base_image_path}'...")

        target_path = Path(target_path)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        if target_path.exists():
            target_path.unlink()

        cmd = Qcow2Manager.build_create_cow_image_command(base_image_path, target_path)
        Qcow2Manager._run(cmd, timeout=timeout)

    @staticmethod
    def _run(cmd, timeout=None):
        try:
            subprocess.run(
                cmd,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                errors="replace",
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as e:
            stderr = e.stderr.strip() if e.stderr else ""
            raise Qcow2ImageError(
                f"qemu-img timed out after {timeout}s creating copy-on-write image"
                + (f"\nPartial stderr: {stderr}")
            )
        except subprocess.CalledProcessError as e:
            stderr = e.stderr.strip() if e.stderr else "Unknown qemu-img error"
            raise Qcow2ImageError(f"Failed to create copy-on-write image: {stderr}")
