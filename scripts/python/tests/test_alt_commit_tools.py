#!/usr/bin/python3
# -*- coding: utf-8 -*-

import io
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path

# Locate repository root and scripts directory
TESTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TESTS_DIR.parents[2]
ALT_COMMITS_DIR = REPO_ROOT / "scripts" / "alt-commits"

if str(ALT_COMMITS_DIR) not in sys.path:
    sys.path.insert(0, str(ALT_COMMITS_DIR))

import alt_lib


class TestRepoResolution(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="alt_test_repo_")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_resolve_repo_path_explicit_valid(self):
        subprocess.check_call(["git", "init", "--quiet", self.tmpdir])
        resolved = alt_lib.resolve_repo_path(self.tmpdir)
        self.assertEqual(resolved, os.path.realpath(self.tmpdir))

    def test_resolve_repo_path_nonexistent(self):
        nonexistent = os.path.join(self.tmpdir, "does_not_exist")
        with redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as cm:
                alt_lib.resolve_repo_path(nonexistent)
        self.assertEqual(cm.exception.code, 1)

    def test_resolve_repo_path_not_a_git_repo(self):
        with redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as cm:
                alt_lib.resolve_repo_path(self.tmpdir)
        self.assertEqual(cm.exception.code, 1)

    def test_get_default_repo_path(self):
        discovered = alt_lib.get_default_repo_path()
        if discovered is not None:
            self.assertTrue(os.path.isdir(discovered))


class TestIgnoreFileHandling(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="alt_test_ignore_")
        self.git_dir = os.path.join(self.tmpdir, "fake_git")
        os.makedirs(self.git_dir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_save_and_load_ignored_shas(self):
        ignore_file = os.path.join(self.tmpdir, "ignored.txt")
        shas = {"aaaabbbbcccc1111222233334444555566667777", "1111222233334444555566667777888899990000"}
        alt_lib.save_ignored_shas(ignore_file, shas)

        loaded_shas, resolved_path = alt_lib.load_ignored_shas(self.git_dir, ignore_file)
        self.assertEqual(loaded_shas, shas)
        self.assertEqual(resolved_path, ignore_file)

    def test_load_ignored_shas_comments_and_normalization(self):
        ignore_file = os.path.join(self.tmpdir, "ignored_mixed.txt")
        with open(ignore_file, "w") as f:
            f.write("# This is a comment\n")
            f.write("  \n")
            f.write("ABCDEF1234567890abcdef1234567890abcdef12  \n")
            f.write("# Another comment\n")
            f.write("fedcba0987654321fedcba0987654321fedcba09\n")

        loaded_shas, _ = alt_lib.load_ignored_shas(self.git_dir, ignore_file)
        self.assertEqual(
            loaded_shas,
            {
                "abcdef1234567890abcdef1234567890abcdef12",
                "fedcba0987654321fedcba0987654321fedcba09",
            },
        )

    def test_load_ignored_shas_nonexistent(self):
        ignore_file = os.path.join(self.tmpdir, "nonexistent.txt")
        loaded_shas, resolved_path = alt_lib.load_ignored_shas(self.git_dir, ignore_file)
        self.assertEqual(loaded_shas, set())
        self.assertEqual(resolved_path, ignore_file)


class TestFileLock(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="alt_test_lock_")
        self.lock_path = os.path.join(self.tmpdir, "test.lock")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_lock_lifecycle_and_contention(self):
        lock1 = alt_lib.FileLock(self.lock_path)
        lock2 = alt_lib.FileLock(self.lock_path)

        # Acquire lock1
        self.assertTrue(lock1.acquire(blocking=False))

        # Contention: lock2 should fail to acquire non-blocking
        self.assertFalse(lock2.acquire(blocking=False))

        # Release lock1
        lock1.release()

        # Now lock2 should successfully acquire
        self.assertTrue(lock2.acquire(blocking=False))
        lock2.release()


class TestDbAndCliExecution(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="alt_test_db_")
        self.db_path = os.path.join(self.tmpdir, "test.db")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_db_connection_and_busy_timeout(self):
        conn = alt_lib.get_db_connection(self.db_path)
        cur = conn.cursor()
        cur.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, name TEXT);")
        cur.execute("INSERT INTO test (name) VALUES (?);", ("cherry-pick",))
        conn.commit()

        cur.execute("SELECT name FROM test WHERE id = 1;")
        row = cur.fetchone()
        self.assertEqual(row[0], "cherry-pick")
        conn.close()

    def test_cli_help_options(self):
        tools = ["alt-lookup", "alt-scan", "alt-browser"]
        for tool in tools:
            tool_path = ALT_COMMITS_DIR / tool
            res = subprocess.run(
                [sys.executable, str(tool_path), "--help"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
            )
            self.assertEqual(
                res.returncode,
                0,
                f"{tool} --help failed with stderr: {res.stderr}",
            )
            self.assertIn("usage:", res.stdout.lower())

    def test_alt_lookup_stats_with_empty_db(self):
        with tempfile.NamedTemporaryFile(suffix=".db") as tmp_db, \
             tempfile.NamedTemporaryFile(suffix=".txt") as tmp_ign:
            conn = sqlite3.connect(tmp_db.name)
            conn.execute(
                "CREATE TABLE hashes (hash_value BLOB PRIMARY KEY, group_id INTEGER, detection_type INTEGER);"
            )
            conn.execute("CREATE TABLE state (key TEXT PRIMARY KEY, value TEXT);")
            conn.execute("INSERT INTO state (key, value) VALUES ('algorithm_version', ?);", (str(alt_lib.ALGORITHM_VERSION),))
            conn.commit()
            conn.close()

            tool_path = ALT_COMMITS_DIR / "alt-lookup"
            res = subprocess.run(
                [
                    sys.executable,
                    str(tool_path),
                    "--db",
                    tmp_db.name,
                    "--ignored",
                    tmp_ign.name,
                    "stats",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
            )
            self.assertEqual(res.returncode, 0, f"alt-lookup stats failed: {res.stderr}")
            self.assertIn("DATABASE METRICS & STATISTICS", res.stdout)
            self.assertIn("Total Linked Hashes:  0", res.stdout)

    def test_get_db_algorithm_version(self):
        self.assertEqual(alt_lib.get_db_algorithm_version("/nonexistent/test.db"), 0)

        with tempfile.NamedTemporaryFile(suffix=".db") as tmp_db:
            conn = sqlite3.connect(tmp_db.name)
            conn.execute("CREATE TABLE state (key TEXT PRIMARY KEY, value TEXT);")
            conn.commit()
            conn.close()
            self.assertEqual(alt_lib.get_db_algorithm_version(tmp_db.name), 0)

            conn = sqlite3.connect(tmp_db.name)
            conn.execute("INSERT INTO state (key, value) VALUES ('algorithm_version', '42');")
            conn.commit()
            conn.close()
            self.assertEqual(alt_lib.get_db_algorithm_version(tmp_db.name), 42)


class TestEndToEndCherryPickPipeline(unittest.TestCase):
    """
    Tests full repository scanning, all 3 cherry-pick detection heuristics,
    and database querying against an isolated synthetic Git repository.
    """

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="alt_pipeline_")
        self.repo_dir = os.path.join(self.test_dir, "repo")
        self.db_path = os.path.join(self.test_dir, "test.db")
        os.makedirs(self.repo_dir)

        self.git_env = {
            **os.environ,
            "GIT_AUTHOR_NAME": "Test Author",
            "GIT_AUTHOR_EMAIL": "author@example.com",
            "GIT_COMMITTER_NAME": "Test Committer",
            "GIT_COMMITTER_EMAIL": "committer@example.com",
            "GIT_AUTHOR_DATE": "1600000000 +0000",
            "GIT_COMMITTER_DATE": "1600000000 +0000",
        }

        def git_run(*args, extra_env=None):
            e = {**self.git_env, **(extra_env or {})}
            subprocess.check_call(
                ["git", "-C", self.repo_dir, *args],
                env=e,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

        # Baseline commit
        subprocess.check_call(["git", "init", "--quiet", self.repo_dir], env=self.git_env)
        code_file = os.path.join(self.repo_dir, "net.c")
        with open(code_file, "w") as f:
            f.write("int active = 0;\n")
        git_run("add", ".")
        git_run("commit", "-m", "Initial baseline")

        # 1. Group 1: Commit A and Commit B (Rank 1: Explicit cherry-pick tag)
        with open(code_file, "a") as f:
            f.write("int fix_leak = 1;\n")
        git_run("commit", "-am", "net: fix memory leak")
        self.sha_a = self._get_rev("HEAD")

        with open(code_file, "a") as f:
            f.write("/* cherry-pick note */\n")
        git_run("commit", "-am", f"net: fix memory leak\n\n(cherry picked from commit {self.sha_a})")
        self.sha_b = self._get_rev("HEAD")

        # 2. Group 2: Commit X and Commit Y (Rank 2: Identical patch diff, no tag)
        fs_file = os.path.join(self.repo_dir, "fs.c")
        with open(fs_file, "w") as f:
            f.write("int count = 10;\n")
        git_run("add", ".")
        git_run("commit", "-m", "fs: optimize read path")
        self.sha_x = self._get_rev("HEAD")

        env_rank2 = {
            "GIT_AUTHOR_DATE": "1600000500 +0000",
            "GIT_COMMITTER_DATE": "1600000500 +0000",
        }
        git_run("checkout", "-b", "branch-rank2", "HEAD~2")
        with open(fs_file, "w") as f:
            f.write("int count = 10;\n")
        git_run("add", ".", extra_env=env_rank2)
        git_run("commit", "-m", "fs: optimize read path", extra_env=env_rank2)
        self.sha_y = self._get_rev("HEAD")

        git_run("checkout", "master")
        git_run("merge", "--no-ff", "-m", "Merge branch-rank2", "branch-rank2")

        # 3. Group 3: Commit M and Commit S (Rank 3: Identical subject + author date, differing diffs)
        drv_file = os.path.join(self.repo_dir, "driver.c")
        with open(drv_file, "w") as f:
            f.write("int drv_state = 1;\n")
        git_run("add", ".")
        git_run("commit", "-m", "driver: baseline")

        with open(drv_file, "a") as f:
            f.write("int lock_v1 = 1;\n")
        git_run("commit", "-am", "driver: fix race condition")
        self.sha_m = self._get_rev("HEAD")

        env_rank3 = {
            "GIT_AUTHOR_DATE": "1600000000 +0000",  # Same author date as git_env
            "GIT_COMMITTER_DATE": "1600000800 +0000",  # Different committer date
        }
        git_run("checkout", "-b", "branch-rank3", "HEAD~2")
        with open(drv_file, "w") as f:
            f.write("int lock_v2 = 2;\nint extra = 3;\n")  # Different diff to avoid Rank 2 match
        git_run("add", ".", extra_env=env_rank3)
        git_run("commit", "-m", "driver: fix race condition", extra_env=env_rank3)
        self.sha_s = self._get_rev("HEAD")

        git_run("checkout", "master")
        git_run("merge", "-s", "ours", "-m", "Merge branch-rank3", "branch-rank3")

        # Run alt-scan to detect all groups
        scan_tool = ALT_COMMITS_DIR / "alt-scan"
        res_scan = subprocess.run(
            [sys.executable, str(scan_tool), self.repo_dir, "--db", self.db_path, "--quiet"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
        )
        self.assertEqual(res_scan.returncode, 0, f"alt-scan failed: {res_scan.stderr}")

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def _get_rev(self, rev: str) -> str:
        return subprocess.check_output(
            ["git", "-C", self.repo_dir, "rev-parse", rev],
            env=self.git_env,
        ).decode().strip()

    def test_cherry_pick_tag_match(self):
        """Validates Rank 1 explicit tag match between Commit A and Commit B."""
        lookup_tool = ALT_COMMITS_DIR / "alt-lookup"

        # Pairwise comparison should exit with 0 (match)
        res_cmp = subprocess.run(
            [sys.executable, str(lookup_tool), "--db", self.db_path, "--no-scan", self.sha_a, self.sha_b],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
        )
        self.assertEqual(res_cmp.returncode, 0, f"Expected match between sha_a and sha_b: {res_cmp.stderr}")

        # Single SHA lookup should return the sibling SHA
        res_lookup = subprocess.run(
            [sys.executable, str(lookup_tool), "--db", self.db_path, "--no-scan", self.sha_a],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
        )
        self.assertEqual(res_lookup.returncode, 0)
        self.assertIn(self.sha_b, res_lookup.stdout)

    def test_patch_id_diff_match(self):
        """Validates Rank 2 patch-id diff match between Commit X and Commit Y."""
        lookup_tool = ALT_COMMITS_DIR / "alt-lookup"
        res = subprocess.run(
            [sys.executable, str(lookup_tool), "--db", self.db_path, "--no-scan", self.sha_x, self.sha_y],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
        )
        self.assertEqual(res.returncode, 0, f"Expected patch diff match between sha_x and sha_y: {res.stderr}")

    def test_subject_and_timestamp_match(self):
        """Validates Rank 3 subject & author timestamp match between Commit M and Commit S."""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT detection_type FROM hashes WHERE hash_value = ?", (bytes.fromhex(self.sha_m),))
        row = cur.fetchone()
        conn.close()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], int(alt_lib.DetectionType.SUBJECT_AND_TIMESTAMP))

        lookup_tool = ALT_COMMITS_DIR / "alt-lookup"

        # Default query includes types 1-3, so they should match
        res = subprocess.run(
            [sys.executable, str(lookup_tool), "--db", self.db_path, "--no-scan", self.sha_m, self.sha_s],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
        )
        self.assertEqual(res.returncode, 0, f"Expected Rank 3 match: {res.stderr}")

        # Filter excluding type 3 (-t 2) should fail to match
        res_filtered = subprocess.run(
            [sys.executable, str(lookup_tool), "--db", self.db_path, "--no-scan", "-t", "2", self.sha_m, self.sha_s],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
        )
        self.assertEqual(res_filtered.returncode, 1, "Expected -t 2 filter to exclude Rank 3 match")

    def test_unrelated_commits_mismatch(self):
        """Validates that commits belonging to different groups exit with code 1."""
        lookup_tool = ALT_COMMITS_DIR / "alt-lookup"
        res = subprocess.run(
            [sys.executable, str(lookup_tool), "--db", self.db_path, "--no-scan", self.sha_a, self.sha_x],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
        )
        self.assertEqual(res.returncode, 1, "Expected mismatch between commits in different groups")

    def test_group_lookup(self):
        """Validates looking up commits by Group ID directly."""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT group_id FROM hashes WHERE hash_value = ?", (bytes.fromhex(self.sha_a),))
        row = cur.fetchone()
        conn.close()
        self.assertIsNotNone(row)
        gid = row[0]

        lookup_tool = ALT_COMMITS_DIR / "alt-lookup"
        res = subprocess.run(
            [sys.executable, str(lookup_tool), "--db", self.db_path, "--no-scan", "-g", str(gid)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
        )
        self.assertEqual(res.returncode, 0)
        self.assertIn(self.sha_a, res.stdout)
        self.assertIn(self.sha_b, res.stdout)

    def test_rebuild_and_outdated_version_auto_scan(self):
        """Validates that algorithm_version is tracked and that outdated DB version triggers auto-rebuild."""
        self.assertEqual(alt_lib.get_db_algorithm_version(self.db_path), alt_lib.ALGORITHM_VERSION)

        conn = sqlite3.connect(self.db_path)
        conn.execute("UPDATE state SET value = '0' WHERE key = 'algorithm_version';")
        dummy_sha = bytes.fromhex("1111111111111111111111111111111111111111")
        conn.execute("INSERT INTO hashes (hash_value, group_id, detection_type) VALUES (?, 99999, 1);", (dummy_sha,))
        conn.commit()
        conn.close()

        self.assertEqual(alt_lib.get_db_algorithm_version(self.db_path), 0)

        lookup_tool = ALT_COMMITS_DIR / "alt-lookup"
        res = subprocess.run(
            [sys.executable, str(lookup_tool), "--db", self.db_path, self.sha_a, self.sha_b],
            env={**self.git_env, "LINUX_GIT": self.repo_dir},
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
        )
        self.assertEqual(res.returncode, 0, f"alt-lookup auto-rebuild failed: {res.stderr}")
        self.assertEqual(res.stderr, "")
        self.assertEqual(alt_lib.get_db_algorithm_version(self.db_path), alt_lib.ALGORITHM_VERSION)

        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT group_id FROM hashes WHERE hash_value = ?", (dummy_sha,))
        self.assertIsNone(cur.fetchone())
        conn.close()


if __name__ == "__main__":
    unittest.main()
