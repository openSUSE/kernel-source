import shutil
from pathlib import Path
import pygit2
from pygit2 import Oid, Tree, Blob, Reference, Branch, InvalidSpecError, GitError
from pygit2 import Object as GitObject

from libs.console import get_logger

logger = get_logger(__name__)


class Repository(pygit2.Repository):
    def __init__(self, path, **kwargs):
        # GitError will be raised if the repository is not found or invalid
        super().__init__(str(path), **kwargs)

    def get_obj(self, input_obj):
        """
        Look up any input (String, Bytes, Oid, Reference, Branch)
        into a repository GitObject. Returns None if lookup fails.
        """
        if input_obj is None:
            return None

        if isinstance(input_obj, GitObject):
            input_obj = input_obj.id
        elif isinstance(input_obj, Reference):
            input_obj = input_obj.raw_target
        elif isinstance(input_obj, Branch):
            input_obj = input_obj.peel().id

        try:
            if isinstance(input_obj, (str, bytes)):
                return self.revparse_single(input_obj)
            if isinstance(input_obj, Oid):
                return self.get(input_obj)
        except (KeyError, InvalidSpecError, GitError):
            pass
        return None

    def get_blob(self, input, filepath=None):
        """
        get_blob:
            Translates whatever the user gave as `Blob` object.
            Returns a `Blob` object or `None` if the lookup/peel fails.
            Raises `ValueError` if filepath is not supplied (except for blob object as input)
        Ex:
        repo.get_blob(tree_obj, "rpm/config.sh")
        repo.get_blob(commit_obj,"rpm/config.sh")
        repo.get_blob("master","rpm/config.sh")
        repo.get_blob(blob_obj)
        """
        obj = self.get_obj(input)

        if isinstance(obj, (Blob, type(None))):
            return obj

        # At this point the obj (Commit | Tag | Tree) will peel further to a Tree
        obj = obj.peel(Tree)

        if not filepath:
            raise ValueError("filepath must be supplied to get the blob")
        try:
            obj = obj[filepath]
            return obj
        except KeyError:
            # KeyError: `filepath` not found in the given reference/object: `input`
            pass
        return None

    def resolve_ref(self, ref):
        """
        Resolve a tag/branch/commit to full SHA
        Raises ValueError if the reference cannot be resolved.
        """
        try:
            commit, _ = self.resolve_refish(ref)
            return str(commit.id)
        except (GitError, KeyError, TypeError) as e:
            raise ValueError(f"Could not resolve git reference '{ref}': {e}")

    def parse_config_sh(self, target):
        """
        Parser - target's rpm/config.sh
        """
        config_sh_vars_dict = {}
        filepath = "rpm/config.sh"
        config_sh_content = self.get_blob(target, filepath)
        if not config_sh_content:
            return config_sh_vars_dict
        lines = config_sh_content.data.decode("utf-8", errors="ignore").splitlines()
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip()
                # Strip quotes if present
                if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                    val = val[1:-1]
                config_sh_vars_dict[key] = val

        return config_sh_vars_dict

    def prune_stale_worktrees(self):
        """
        git worktree prune
        """
        for wt_name in self.list_worktrees():
            try:
                wt = self.lookup_worktree(wt_name)
                if wt.is_prunable:
                    wt.prune(True)
                    logger.debug(f"Pruned stale worktree '{wt_name}'")
            except Exception as e:
                logger.debug(f"Failed to prune worktree '{wt_name}': {e}")
                continue

    def create_worktree(self, commit_ref, cache_dir):
        """
        Create a git worktree.
        FIXME: make it generic, cuurently too specific to workspace
        """
        commit_hash = self.resolve_ref(commit_ref)
        workspace_dir = Path(cache_dir) / "workspaces" / commit_hash
        branch_name = f"kernel-sandbox-{commit_hash[:8]}"

        self.prune_stale_worktrees()

        if workspace_dir.exists():
            logger.debug(f"Reusing existing worktree at {workspace_dir}")
            return workspace_dir

        logger.info(f"Creating worktree for {commit_hash} at {workspace_dir}")
        workspace_dir.parent.mkdir(parents=True, exist_ok=True)
        try:
            commit_obj = self.get(commit_hash)

            if branch_name in self.branches.local:
                self.branches.local.delete(branch_name)

            branch = self.branches.local.create(branch_name, commit_obj)

            self.add_worktree(commit_hash, str(workspace_dir), branch)
            return workspace_dir
        except GitError as e:
            shutil.rmtree(workspace_dir, ignore_errors=True)
            raise GitError(f"Failed to create worktree environment: {e}")

    def cleanup_worktree(self, workspace_dir):
        """
        Remove a git worktree.
        FIXME: make it generic, cuurently too specific to workspace
        """
        target_path = Path(workspace_dir)
        worktree_name = target_path.name
        logger.info(f"Cleaning up worktree at {target_path}")
        shutil.rmtree(target_path, ignore_errors=True)

        if worktree_name in self.list_worktrees():
            wt = self.lookup_worktree(worktree_name)
            wt.prune(True)
