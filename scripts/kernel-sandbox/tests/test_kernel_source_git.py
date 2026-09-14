import shutil
import tempfile
import unittest
from pathlib import Path
import pygit2
from pygit2 import Commit, Blob
from libs.kernel_source_git import Repository


class TestKernelRepository(unittest.TestCase):
    def setUp(self):
        tmp_dir_ctx = tempfile.TemporaryDirectory()
        self.addCleanup(tmp_dir_ctx.cleanup)
        self.tmp_dir = tmp_dir_ctx.name
        self.repo_path = Path(self.tmp_dir) / "test_repo"
        self.repo = pygit2.init_repository(str(self.repo_path), bare=False)
        self.repo = Repository(self.repo_path)
        self.sig = pygit2.Signature("testuser", "testuser@suse.de")
        tb = self.repo.TreeBuilder()

        # Exact real-world config content
        self.config_content = (
            "# The version of the main tarball to use\n"
            "SRCVERSION=6.12\n"
            "# variant of the kernel-source package, either empty or \"-rt\"\n"
            "VARIANT=\n"
            "# enable kernel module compression\n"
            "COMPRESS_MODULES=\"zstd\"\n"
            "COMPRESS_VMLINUX=\"xz\"\n"
            "# Compile binary devicetrees on master and stable branches.\n"
            "BUILD_DTBS=\"Yes\"\n"
            "# Generate a _multibuild file\n"
            "MULTIBUILD=\"Yes\"\n"
            "# Use new style livepatch package names\n"
            "LIVEPATCH=livepatch\n"
            "# Enable livepatching related packages on -rt variant\n"
            "LIVEPATCH_RT=1\n"
            "# buildservice projects to build the kernel against\n"
            "OBS_PROJECT=SUSE:SLFO:Main\n"
            "IBS_PROJECT=SUSE:SLFO:Main\n"
            "# Bugzilla info\n"
            "BUGZILLA_SERVER=\"apibugzilla.suse.com\"\n"
            "BUGZILLA_PRODUCT=\"SUSE Linux Enterprise Server 16.1\"\n"
            "BUGZILLA_COMPONENT=\"Kernel\"\n"
            "SPLIT_OPTIONAL=Yes\n"
            "SUPPORTED_MODULES_CHECK=Yes\n"
            "# build documentation in HTML format\n"
            "BUILD_HTML=Yes\n"
            "# build documentation in PDF format\n"
            "BUILD_PDF=No\n"
            "# Generate compile_commands.json\n"
            "GENERATE_COMPILE_COMMANDS=Yes\n"
            "# Set gcc version to the one used for build in IBS\n"
            "GCC_VERSION=13\n"
            "# Use the new kABI tool\n"
            "USE_SUSE_KABI_TOOLS=Yes\n"
        )
        config_blob_oid = self.repo.create_blob(self.config_content.encode("utf-8"))
        rpm_tb = self.repo.TreeBuilder()
        rpm_tb.insert("config.sh", config_blob_oid, pygit2.GIT_FILEMODE_BLOB)
        rpm_tree_oid = rpm_tb.write()
        tb.insert("rpm", rpm_tree_oid, pygit2.GIT_FILEMODE_TREE)
        root_tree_oid = tb.write()
        self.commit_id = self.repo.create_commit(
            "refs/heads/master",
            self.sig,
            self.sig,
            "Initial setup commit with real config",
            root_tree_oid,
            []
        )
        self.repo.set_head("refs/heads/master")

    def test_get_obj(self):
        obj = self.repo.get_obj("master")
        self.assertIsNotNone(obj)
        self.assertIsInstance(obj, Commit)
        self.assertEqual(obj.id, self.commit_id)

        ref = self.repo.references.get("refs/heads/master")
        obj_ref = self.repo.get_obj(ref)
        self.assertEqual(obj_ref.id, self.commit_id)
        self.assertIsNone(self.repo.get_obj("invalid-branch"))

    def test_get_blob(self):
        blob = self.repo.get_blob("master", "rpm/config.sh")
        self.assertIsInstance(blob, Blob)
        self.assertIn(b"SRCVERSION", blob.data)
        self.assertIsNone(self.repo.get_blob("master", "non_existent_file.txt"))
        with self.assertRaises(ValueError):
            self.repo.get_blob("master", filepath=None)

    def test_resolve_ref(self):
        resolved_sha = self.repo.resolve_ref("master")
        self.assertEqual(resolved_sha, str(self.commit_id))

        with self.assertRaises(ValueError):
            self.repo.resolve_ref("non_existent_tag_or_branch")

    def test_parse_config_sh_variables(self):
        config_vars = self.repo.parse_config_sh("master")
        self.assertEqual(config_vars.get("SRCVERSION"), "6.12")
        self.assertEqual(config_vars.get("VARIANT"), "")
        self.assertEqual(config_vars.get("LIVEPATCH"), "livepatch")
        self.assertEqual(config_vars.get("BUGZILLA_SERVER"), "apibugzilla.suse.com")
        self.assertEqual(config_vars.get("BUGZILLA_PRODUCT"), "SUSE Linux Enterprise Server 16.1")
        self.assertEqual(config_vars.get("OBS_PROJECT"), "SUSE:SLFO:Main")
        self.assertEqual(config_vars.get("IBS_PROJECT"), "SUSE:SLFO:Main")
        self.assertNotIn("The version of the main tarball to use", config_vars)
        self.assertNotIn("variant of the kernel-source package", config_vars)

    def test_create_and_cleanup_worktree(self):
        cache_root = Path(self.tmp_dir) / "cache"
        workspace_dir = self.repo.create_worktree("master", cache_root)
        self.assertTrue(workspace_dir.exists())
        self.assertTrue((workspace_dir / "rpm" / "config.sh").exists())

        # cache-hit
        second_run_dir = self.repo.create_worktree("master", cache_root)
        self.assertEqual(workspace_dir, second_run_dir)

        # Cleanup the worktree and ensure it is removed from the host
        self.repo.cleanup_worktree(workspace_dir)
        self.assertFalse(workspace_dir.exists())
        self.assertNotIn(workspace_dir.name, self.repo.list_worktrees())

    def test_create_worktree_unresolvable_ref_raises(self):
        """an unresolvable commit ref must surface as ValueError,
        not proceed to create a worktree from garbage."""
        cache_root = Path(self.tmp_dir) / "cache"
        with self.assertRaises(ValueError):
            self.repo.create_worktree("no-such-ref", cache_root)
        self.assertFalse((cache_root / "workspaces").exists())

    def test_create_worktree_reuses_stale_branch_name(self):
        """a branch named 'kernel-sandbox-<sha>' already exists
        (left over from a worktree whose directory was deleted outside
        this tool) and must be deleted and recreated pointing at the right
        commit, not left stale or causing a create failure."""
        cache_root = Path(self.tmp_dir) / "cache"
        commit_hash = str(self.commit_id)
        branch_name = f"kernel-sandbox-{commit_hash[:8]}"

        # Pre-create a branch with the same name via a second, unrelated commit
        second_tb = self.repo.TreeBuilder()
        second_tree_oid = second_tb.write()
        second_commit_id = self.repo.create_commit(
            None, self.sig, self.sig, "second commit", second_tree_oid, []
        )
        self.repo.branches.local.create(branch_name, self.repo.get(second_commit_id))

        workspace_dir = self.repo.create_worktree("master", cache_root)
        self.assertTrue(workspace_dir.exists())
        self.assertEqual(self.repo.branches.local[branch_name].target, self.commit_id)

    def test_cleanup_worktree_on_unregistered_path_does_not_raise(self):
        """cleaning up a directory that was never a registered
        git worktree must not crash - just removes the directory."""
        not_a_worktee_dir = Path(self.tmp_dir) / "not-a-worktree"
        not_a_worktee_dir.mkdir()
        self.repo.cleanup_worktree(not_a_worktee_dir)
        self.assertFalse(not_a_worktee_dir.exists())

    def test_prune_stale_worktrees_removes_orphaned_entry(self):
        """a worktree whose directory was deleted by hand is detected as prunable and removed"""
        cache_root = Path(self.tmp_dir) / "cache"
        workspace_dir = self.repo.create_worktree("master", cache_root)
        worktree_name = workspace_dir.name
        self.assertIn(worktree_name, self.repo.list_worktrees())

        # orphaned worktree: directory gone, git meta remains
        shutil.rmtree(workspace_dir)

        self.repo.prune_stale_worktrees()
        self.assertNotIn(worktree_name, self.repo.list_worktrees())
