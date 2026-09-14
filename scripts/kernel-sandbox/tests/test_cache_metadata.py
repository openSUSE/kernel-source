import json
import tempfile
import unittest
from pathlib import Path
from libs.cache_metadata import discover_cached_builds, read_cache_metadata, write_cache_metadata


class TestWriteReadCacheMetadata(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.artifacts_dir = Path(self.tmp_dir.name) / "build_artifacts" / "abc1234def" / "x86_64" / "default"

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_write_then_read_roundtrip(self):
        write_cache_metadata(
            self.artifacts_dir, mode="fast", arch="x86_64", config_flavor="default",
            commit_hash="abc1234def", kernel_image_name="vmlinuz")

        metadata = read_cache_metadata(self.artifacts_dir)
        self.assertEqual(metadata["mode"], "fast")
        self.assertEqual(metadata["arch"], "x86_64")
        self.assertEqual(metadata["config_flavor"], "default")
        self.assertEqual(metadata["commit_hash"], "abc1234def")
        self.assertEqual(metadata["kernel_image_name"], "vmlinuz")
        self.assertIsNone(metadata["rpm_arch"])
        self.assertIn("updated_at", metadata)

    def test_write_creates_missing_artifacts_dir(self):
        self.assertFalse(self.artifacts_dir.exists())
        write_cache_metadata(self.artifacts_dir, mode="rpm", arch="x86_64", config_flavor="default", commit_hash="abc1234def")
        self.assertTrue(self.artifacts_dir.exists())

    def test_read_missing_file_returns_none(self):
        self.assertIsNone(read_cache_metadata(self.artifacts_dir))

    def test_read_corrupt_json_returns_none(self):
        self.artifacts_dir.mkdir(parents=True)
        (self.artifacts_dir / ".cache_meta.json").write_text("{not valid json")
        self.assertIsNone(read_cache_metadata(self.artifacts_dir))

    def test_rewriting_updates_timestamp_and_fields(self):
        write_cache_metadata(self.artifacts_dir, mode="fast", arch="x86_64", config_flavor="default", commit_hash="abc1234def")
        first = read_cache_metadata(self.artifacts_dir)

        write_cache_metadata(self.artifacts_dir, mode="fast", arch="x86_64", config_flavor="default", commit_hash="abc1234def")
        second = read_cache_metadata(self.artifacts_dir)

        self.assertGreaterEqual(second["updated_at"], first["updated_at"])


class TestDiscoverCachedBuilds(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.cache_dir = Path(self.tmp_dir.name)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def _artifacts_dir(self, commit_hash, arch, config_flavor):
        return self.cache_dir / "build_artifacts" / commit_hash / arch / config_flavor

    def test_no_build_artifacts_dir_returns_empty_list(self):
        self.assertEqual(discover_cached_builds(self.cache_dir), [])

    def test_fast_mode_entry_marked_not_ready_when_artifacts_missing(self):
        artifacts_dir = self._artifacts_dir("abc1234def", "x86_64", "default")
        write_cache_metadata(
            artifacts_dir, mode="fast", arch="x86_64", config_flavor="default",
            commit_hash="abc1234def", kernel_image_name="vmlinuz")

        entries = discover_cached_builds(self.cache_dir)
        self.assertEqual(len(entries), 1)
        self.assertFalse(entries[0]["boot_ready"])

    def test_fast_mode_entry_marked_ready_when_kernel_and_initrd_present(self):
        artifacts_dir = self._artifacts_dir("abc1234def", "x86_64", "default")
        write_cache_metadata(
            artifacts_dir, mode="fast", arch="x86_64", config_flavor="default",
            commit_hash="abc1234def", kernel_image_name="vmlinuz")
        (artifacts_dir / "vmlinuz").write_text("mock-kernel")
        (artifacts_dir / "initrd_custom.gz").write_text("mock-initrd")

        entries = discover_cached_builds(self.cache_dir)
        self.assertTrue(entries[0]["boot_ready"])

    def test_rpm_mode_entry_marked_ready_when_cow_image_present(self):
        artifacts_dir = self._artifacts_dir("abc1234def", "x86_64", "kvmsmall")
        write_cache_metadata(
            artifacts_dir, mode="rpm", arch="x86_64", config_flavor="kvmsmall",
            commit_hash="abc1234def", rpm_arch="x86_64")

        base_images_dir = self.cache_dir / "base-images"
        base_images_dir.mkdir(parents=True)
        (base_images_dir / "temp-sandbox-gabc1234-kvmsmall.x86_64.qcow2").write_text("mock-qcow2")

        entries = discover_cached_builds(self.cache_dir)
        self.assertTrue(entries[0]["boot_ready"])

    def test_rpm_mode_entry_marked_not_ready_when_cow_image_missing(self):
        artifacts_dir = self._artifacts_dir("abc1234def", "x86_64", "kvmsmall")
        write_cache_metadata(
            artifacts_dir, mode="rpm", arch="x86_64", config_flavor="kvmsmall",
            commit_hash="abc1234def", rpm_arch="x86_64")

        entries = discover_cached_builds(self.cache_dir)
        self.assertFalse(entries[0]["boot_ready"])

    def test_entries_sorted_most_recently_updated_first(self):
        older = self._artifacts_dir("commit1", "x86_64", "default")
        newer = self._artifacts_dir("commit2", "x86_64", "default")
        write_cache_metadata(older, mode="fast", arch="x86_64", config_flavor="default", commit_hash="commit1")
        write_cache_metadata(newer, mode="fast", arch="x86_64", config_flavor="default", commit_hash="commit2")

        # force a deterministic ordering rather than relying on real-clock ties
        older_meta = read_cache_metadata(older)
        older_meta["updated_at"] = "2020-01-01T00:00:00+00:00"
        with open(older / ".cache_meta.json", "w", encoding="utf-8") as f:
            json.dump(older_meta, f)

        entries = discover_cached_builds(self.cache_dir)
        self.assertEqual(entries[0]["commit_hash"], "commit2")
        self.assertEqual(entries[1]["commit_hash"], "commit1")

    def test_ignores_corrupt_metadata_entries(self):
        good = self._artifacts_dir("goodcommit", "x86_64", "default")
        write_cache_metadata(good, mode="fast", arch="x86_64", config_flavor="default", commit_hash="goodcommit")

        bad = self._artifacts_dir("badcommit", "x86_64", "default")
        bad.mkdir(parents=True)
        (bad / ".cache_meta.json").write_text("{not valid json")

        entries = discover_cached_builds(self.cache_dir)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["commit_hash"], "goodcommit")

    def test_unknown_mode_marked_not_ready(self):
        artifacts_dir = self._artifacts_dir("abc1234def", "x86_64", "default")
        write_cache_metadata(artifacts_dir, mode="unknown-mode", arch="x86_64", config_flavor="default", commit_hash="abc1234def")

        entries = discover_cached_builds(self.cache_dir)
        self.assertFalse(entries[0]["boot_ready"])
