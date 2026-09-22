import contextlib
import functools
import http.server
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path

from libs.storage_manager import (
    DownloadError,
    HTTPDownloader,
    ImageFinder,
    ImageNotFoundError,
    JeosBaseUrlStrategy,
    JeosDirectUrlStrategy,
    JeosFallbackStrategy,
    Qcow2ImageError,
    Qcow2Manager,
    StrategyResolver,
    _extract_qcow2_links,
)


class MockHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass


@contextlib.contextmanager
def _local_http_server(directory):
    """Serves `directory` over real HTTP on 127.0.0.1"""
    handler = functools.partial(MockHTTPRequestHandler, directory=str(directory))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


class TestHTTPDownloader(unittest.TestCase):
    def test_download_file_success(self):
        with tempfile.TemporaryDirectory() as serve_dir, tempfile.TemporaryDirectory() as dest_dir:
            Path(serve_dir, "image.qcow2").write_text("qcow2-content")
            with _local_http_server(serve_dir) as base_url:
                dest = Path(dest_dir) / "target.qcow2"
                HTTPDownloader().download_file(f"{base_url}/image.qcow2", dest)
                self.assertEqual(dest.read_text(), "qcow2-content")
                self.assertFalse(dest.with_suffix(dest.suffix + ".tmp").exists())

    def test_download_file_404_raises_and_cleans_tmp(self):
        """a real 404 must be wrapped in DownloadError and leave no partial .tmp file behind."""
        with tempfile.TemporaryDirectory() as serve_dir, tempfile.TemporaryDirectory() as dest_dir:
            with _local_http_server(serve_dir) as base_url:
                dest = Path(dest_dir) / "target.qcow2"
                with self.assertRaises(DownloadError) as ctx:
                    HTTPDownloader().download_file(f"{base_url}/not-existing.qcow2", dest)
                self.assertIn("Download failed", str(ctx.exception))
                self.assertIn("404", str(ctx.exception))
                self.assertFalse(dest.exists())
                self.assertFalse(dest.with_suffix(dest.suffix + ".tmp").exists())

    def test_connection_refused_raises_download_error(self):
        """nothing listening at all, not even a 404."""
        with tempfile.TemporaryDirectory() as dest_dir:
            dest = Path(dest_dir) / "target.qcow2"
            with self.assertRaises(DownloadError) as ctx:
                HTTPDownloader().download_file("http://127.0.0.1:1/image.qcow2", dest)
            self.assertIn("Download failed", str(ctx.exception))
            self.assertIn("Connection refused", str(ctx.exception))

    def test_stale_tmp_file_is_overwritten(self):
        """a leftover .tmp file from a previous crashed run must not block a fresh download."""
        with tempfile.TemporaryDirectory() as serve_dir, tempfile.TemporaryDirectory() as dest_dir:
            Path(serve_dir, "image.qcow2").write_text("qcow2-content")
            dest = Path(dest_dir) / "target.qcow2"
            stale_tmp = dest.with_suffix(dest.suffix + ".tmp")
            stale_tmp.parent.mkdir(parents=True, exist_ok=True)
            stale_tmp.write_text("stale-leftover")
            with _local_http_server(serve_dir) as base_url:
                HTTPDownloader().download_file(f"{base_url}/image.qcow2", dest)
            self.assertEqual(dest.read_text(), "qcow2-content")


class TestExtractQcow2Links(unittest.TestCase):
    def test_extract_qcow2_links_scenarios(self):
        test_cases = [
            (
                "qcow2_hrefs_only",
                '<html><body><a href="a.qcow2">a</a><a href="b.txt">b</a><a href="c.qcow2">c</a></body></html>',
                ["a.qcow2", "c.qcow2"]
            ),
            (
                "ignores_anchors_without_href",
                '<a name="top">Top</a><a href="x.qcow2">x</a>',
                ["x.qcow2"]
            ),
            (
                "no_matches",
                "<html><body>no links here</body></html>",
                []
            ),
            (
                "upper_case_extension_match",
                '<a href="upper.QCOW2">x</a><a href="lower.qcow2">y</a>',
                ["lower.qcow2"]
            ),
            (
                "quoted_hrefs",
                "<a href='single.qcow2'>a</a><a href=\"double.qcow2\">b</a>",
                ["single.qcow2", "double.qcow2"]
            ),
        ]

        for name, html, expected in test_cases:
            with self.subTest(case=name):
                self.assertEqual(_extract_qcow2_links(html), expected)


class TestStrategies(unittest.TestCase):
    def test_direct_url_strategy(self):
        config = {"direct_url": "https://mirrors.suse.org/images/jeos-15.qcow2"}
        strategy = JeosDirectUrlStrategy(config)
        url, filename, requires_parsing = strategy.get_download_url("x86_64")
        self.assertEqual(url, "https://mirrors.suse.org/images/jeos-15.qcow2")
        self.assertEqual(filename, "jeos-15.qcow2")
        self.assertFalse(requires_parsing)

    def test_base_url_strategy(self):
        config = {"base_url": "https://mirrors.suse.org/images/x86_64/"}
        strategy = JeosBaseUrlStrategy(config)
        url, filename, requires_parsing = strategy.get_download_url("x86_64")
        self.assertEqual(url, "https://mirrors.suse.org/images/x86_64/")
        self.assertIsNone(filename)
        self.assertTrue(requires_parsing)

        config = {"base_url": "https://mirrors.suse.org/images"}
        strategy = JeosBaseUrlStrategy(config)
        url, filename, requires_parsing = strategy.get_download_url("aarch64")
        self.assertEqual(url, "https://mirrors.suse.org/images/aarch64/")
        self.assertIsNone(filename)
        self.assertTrue(requires_parsing)

    def test_fallback_strategy(self):
        strategy = JeosFallbackStrategy("openSUSE_Leap_15.5")
        url, filename, requires_parsing = strategy.get_download_url("x86_64")
        self.assertIn("https://download.opensuse.org", url)
        self.assertIn("SUSE:/Templates:/Images:/openSUSE_Leap_15.5", url)
        self.assertIsNone(filename)
        self.assertTrue(requires_parsing)


class TestStrategyResolver(unittest.TestCase):
    def setUp(self):
        self.resolver = StrategyResolver()

    def test_resolves_direct_url_strategy(self):
        mapping = {"direct_url": "https://mirrors.suse.org/images/jeos-15.qcow2"}
        self.assertIsInstance(self.resolver.get_download_strategy(mapping), JeosDirectUrlStrategy)

    def test_resolves_base_url_strategy(self):
        mapping = {"base_url": "https://mirrors.suse.org/images/"}
        self.assertIsInstance(self.resolver.get_download_strategy(mapping), JeosBaseUrlStrategy)

    def test_resolves_fallback_strategy(self):
        self.assertIsInstance(self.resolver.get_download_strategy("some_fallback_template"), JeosFallbackStrategy)


class MockHTTPDownloader:
    """mock for HTTPDownloader that just records calls (no actual network IO),
    so we can test (cache-hit vs. download)"""
    def __init__(self):
        self.calls = []

    def download_file(self, url, dest):
        self.calls.append((url, dest))
        Path(dest).parent.mkdir(parents=True, exist_ok=True)
        Path(dest).write_text("mock-image-content")


class TestDownloadExternalImage(unittest.TestCase):
    def setUp(self):
        self.serve_dir = tempfile.TemporaryDirectory()
        self.cache_dir = tempfile.TemporaryDirectory()
        self.downloader = MockHTTPDownloader()
        self.finder = ImageFinder(downloader=self.downloader, exclude_patterns=["unwanted"])

    def tearDown(self):
        self.serve_dir.cleanup()
        self.cache_dir.cleanup()

    def test_downloads_when_not_cached(self):
        result = self.finder.download_external_image(
            arch="x86_64",
            mapping_entry={"direct_url": "https://example.invalid/images/jeos.x86_64.qcow2"},
            cache_dir=self.cache_dir.name
        )
        self.assertEqual(result.name, "jeos.x86_64.qcow2")
        self.assertEqual(len(self.downloader.calls), 1)

    def test_download_when_cached(self):
        cached = Path(self.cache_dir.name) / "base-images" / "jeos.x86_64.qcow2"
        cached.parent.mkdir(parents=True)
        cached.write_text("qcow2-content")
        result = self.finder.download_external_image(
            arch="x86_64",
            mapping_entry={"direct_url": "https://example.invalid/images/jeos.x86_64.qcow2"},
            cache_dir=self.cache_dir.name
        )
        self.assertEqual(result, cached)
        self.assertEqual(self.downloader.calls, [])

    def test_highest_matching_and_excludes_unwanted(self):
        arch_dir = Path(self.serve_dir.name, "x86_64")
        arch_dir.mkdir()
        (arch_dir / "JeOS-v1.x86_64.qcow2").write_text("v1")
        (arch_dir / "JeOS-v2-unwanted.x86_64.qcow2").write_text("v2")
        (arch_dir / "JeOS-v3.x86_64.qcow2").write_text("v3")
        with _local_http_server(self.serve_dir.name) as base_url:
            result = self.finder.download_external_image(
                arch="x86_64", mapping_entry={"base_url": base_url}, cache_dir=self.cache_dir.name)
        self.assertEqual(result.name, "JeOS-v3.x86_64.qcow2")
        self.assertEqual(len(self.downloader.calls), 1)

    def test_no_matches(self):
        arch_dir = Path(self.serve_dir.name, "x86_64")
        arch_dir.mkdir()
        (arch_dir / "JeOS-v2-unwanted.x86_64.qcow2").write_text("v2")
        with _local_http_server(self.serve_dir.name) as base_url:
            with self.assertRaises(ImageNotFoundError):
                self.finder.download_external_image(
                    arch="x86_64", mapping_entry={"base_url": base_url}, cache_dir=self.cache_dir.name)

    def test_rpm_style_arch_matches_aarch64_filenames(self):
        """Callers must pass the rpm_arch (ex: "aarch64") not linux_arch ("arm64")."""
        arch_dir = Path(self.serve_dir.name, "aarch64")
        arch_dir.mkdir()
        (arch_dir / "JeOS-15.4.aarch64.qcow2").write_text("arm-image")
        with _local_http_server(self.serve_dir.name) as base_url:
            result = self.finder.download_external_image(
                arch="aarch64", mapping_entry={"base_url": base_url}, cache_dir=self.cache_dir.name)
        self.assertEqual(result.name, "JeOS-15.4.aarch64.qcow2")

    def test_linux_arch_style_value_does_not_match(self):
        """passing the linux_arch ("arm64") instead rpm_arch ("aarch64") should raise"""
        arch_dir = Path(self.serve_dir.name, "arm64")
        arch_dir.mkdir()
        (arch_dir / "JeOS-15.4.aarch64.qcow2").write_text("arm-image")
        with _local_http_server(self.serve_dir.name) as base_url:
            with self.assertRaises(ImageNotFoundError):
                self.finder.download_external_image(
                    arch="arm64", mapping_entry={"base_url": base_url}, cache_dir=self.cache_dir.name)

    def test_connection_failure_raises_download_error(self):
        with self.assertRaises(DownloadError):
            self.finder.download_external_image(
                arch="x86_64", mapping_entry={"base_url": "http://127.0.0.1:1"}, cache_dir=self.cache_dir.name)


class TestFindImage(unittest.TestCase):
    def setUp(self):
        self.workdir = tempfile.TemporaryDirectory()
        self.workdir_path = Path(self.workdir.name)
        self.finder = ImageFinder(downloader=MockHTTPDownloader(), exclude_patterns=["unwanted"])

    def tearDown(self):
        self.workdir.cleanup()

    def _create_image(self, parent_dir, filename, content="data"):
        """Helper to set up mock image files"""
        img_path = Path(parent_dir) / filename
        img_path.parent.mkdir(parents=True, exist_ok=True)
        img_path.write_text(content)
        return img_path

    def test_cache_hit_returns_newest_matching_version(self):
        base_images = self.workdir_path / "cache" / "base-images"
        v1 = self._create_image(base_images, "JeOS-15.4.x86_64-v1.qcow2", "old")
        v2 = self._create_image(base_images, "JeOS-15.4.x86_64-v2.qcow2", "new")
        os.utime(v1, (1000, 1000))
        os.utime(v2, (2000, 2000))

        found = self.finder.find_image(
            arch="x86_64",
            target_version="15.4",
            cache_dir=str(self.workdir_path / "cache")
        )
        self.assertEqual(found, v2)

    def test_cache_hit_does_not_false_match_on_cache_dir_path(self):
        """the version check must look at the filename, not the full path"""
        versioned_cache_dir = self.workdir_path / "15.4-workspace"
        self._create_image(versioned_cache_dir / "base-images", "JeOS-16.0.x86_64.qcow2", "unrelated version")

        with self.assertRaises(ImageNotFoundError):
            self.finder.find_image(
                arch="x86_64",
                target_version="15.4",
                cache_dir=str(versioned_cache_dir)
            )

    def test_falls_back_to_local_search_path_after_external_failure(self):
        local_root = self.workdir_path / "ibs"
        match = self._create_image(local_root / "15.4", "JeOS-15.4.x86_64-kvm.qcow2", "local-match")

        found = self.finder.find_image(
            arch="x86_64",
            target_version="15.4",
            cache_dir=str(self.workdir_path / "cache"),
            local_search_path=str(local_root),
            mapping_entry={"base_url": "http://127.0.0.1:1"},
        )
        self.assertEqual(found, match)

    def test_local_search_path_excludes_unwanted_and_wrong_qcow_pattern(self):
        version_dir = self.workdir_path / "ibs" / "15.4"
        self._create_image(version_dir, "JeOS-15.4.x86_64-unwanted.qcow2", "excluded")
        self._create_image(version_dir, "JeOS-15.4.x86_64-vmware.qcow2", "wrong pattern")

        with self.assertRaises(ImageNotFoundError):
            self.finder.find_image(
                arch="x86_64",
                target_version="15.4",
                cache_dir=str(self.workdir_path / "cache"),
                local_search_path=str(self.workdir_path / "ibs")
            )

    def test_missing_local_search_path_directory_does_not_crash(self):
        """local_search_path pointing at a not-existent directory must go through ImageNotFoundError"""
        with self.assertRaises(ImageNotFoundError):
            self.finder.find_image(
                arch="x86_64",
                target_version="15.4",
                cache_dir=str(self.workdir_path / "cache"),
                local_search_path=str(self.workdir_path / "not-existing")
            )

    def test_raises_with_no_sources_available(self):
        with self.assertRaises(ImageNotFoundError) as ctx:
            self.finder.find_image(
                arch="x86_64",
                target_version="15.4",
                cache_dir=str(self.workdir_path / "cache")
            )
        self.assertIn("15.4", str(ctx.exception))


class TestBuildCreateCowImageCommand(unittest.TestCase):
    def test_command_shape(self):
        cmd = Qcow2Manager.build_create_cow_image_command("/src/base.qcow2", "/dest/target.qcow2")
        self.assertEqual(cmd[0], "qemu-img")
        self.assertIn("create", cmd)
        self.assertEqual(cmd[cmd.index("-b") + 1], Path("/src/base.qcow2").resolve())
        self.assertEqual(cmd[-1], Path("/dest/target.qcow2"))


class TestQcow2ManagerRun(unittest.TestCase):
    """checks _run()'s subprocess execution"""
    def test_success_does_not_raise(self):
        Qcow2Manager._run([sys.executable, "-c", "pass"])

    def test_failure_wraps_stderr_into_qcow2imageerror(self):
        with self.assertRaises(Qcow2ImageError) as ctx:
            Qcow2Manager._run([sys.executable, "-c", "import sys; sys.stderr.write('backing file error'); sys.exit(1)"])
        self.assertIn("backing file error", str(ctx.exception))

    def test_timeout_raises_qcow2imageerror(self):
        """a stalled qemu-img must not hang the subprocess run() forever."""
        with self.assertRaises(Qcow2ImageError) as ctx:
            Qcow2Manager._run([sys.executable, "-c", "import time; time.sleep(5)"], timeout=0.3)
        self.assertIn("timed out after 0.3s", str(ctx.exception))

    def test_non_utf8_stderr_does_not_crash(self):
        """non-UTF8 stderr bytes must still raise Qcow2ImageError with text flag(to_string)"""
        with self.assertRaises(Qcow2ImageError) as ctx:
            Qcow2Manager._run(
                [sys.executable, "-c", "import sys; sys.stderr.buffer.write(b'\\377\\376 bad-bytes'); sys.exit(1)"]
            )
        self.assertIn("�� bad-bytes", str(ctx.exception))
