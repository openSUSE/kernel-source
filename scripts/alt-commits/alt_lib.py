#!/usr/bin/env python3

import fcntl
import os
import sqlite3
import subprocess
import sys
from enum import IntEnum
from typing import Dict, Optional, Set, TextIO, Tuple

DB_NAME = "alt-commits.db"
IGNORED_NAME = "alt-commits-ignored.txt"


class DetectionType(IntEnum):
    CHERRY_PICK_TAG = 1        # Rank 1: Explicit '(cherry picked from...)' tag
    SUBJECT_AND_DIFF = 2       # Rank 2: Identical code diff (patch-id) + subject
    SUBJECT_AND_TIMESTAMP = 3  # Rank 3: Identical subject and author timestamp


DETECTION_LABELS: Dict[int, str] = {
    int(DetectionType.CHERRY_PICK_TAG): "Explicit Cherry-Pick Tag",
    int(DetectionType.SUBJECT_AND_DIFF): "Patch Diff (Patch-ID) Match",
    int(DetectionType.SUBJECT_AND_TIMESTAMP): "Subject & Timestamp Match",
}


def format_size(size_bytes: int | float) -> str:
    """Formats file size into human-readable units."""
    bytes_val = float(size_bytes)
    for unit in ["B", "KB", "MB", "GB"]:
        if bytes_val < 1024.0:
            return f"{bytes_val:.2f} {unit}"
        bytes_val /= 1024.0
    return f"{bytes_val:.2f} TB"


def get_default_repo_path() -> Optional[str]:
    """Determines the default path to the mainline Linux git repository via linux_git.sh."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    linux_git_sh = os.path.abspath(os.path.join(script_dir, "..", "linux_git.sh"))
    if os.path.exists(linux_git_sh):
        try:
            res = subprocess.run(
                [linux_git_sh],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                check=True,
            )
            out = res.stdout.strip()
            if out:
                return out
        except Exception:
            pass

    return None


def resolve_repo_path(repo_param: Optional[str] = None) -> str:
    """
    Resolves and validates the Linux kernel Git repository path once at entry.
    Discovers default path via linux_git.sh if repo_param is not provided.
    Exits with error if the repository is not found or is invalid.
    """
    raw_path = repo_param or get_default_repo_path()
    if not raw_path:
        sys.stderr.write(
            'Error: No Linux git repository found (please set the "LINUX_GIT" environment variable).\n'
        )
        sys.exit(1)

    repo_path = os.path.abspath(os.path.expanduser(raw_path))
    if not os.path.exists(repo_path):
        sys.stderr.write(f"Error: Repository path '{repo_path}' does not exist.\n")
        sys.exit(1)

    try:
        subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            cwd=repo_path,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
        )
    except subprocess.CalledProcessError:
        sys.stderr.write(f"Error: Path '{repo_path}' is not a valid Git repository.\n")
        sys.exit(1)

    return repo_path


def resolve_db_path(db_param: Optional[str] = None) -> str:
    """Resolves DB path, defaulting to .git/alt-commits.db inside the kernel-source repository."""
    if db_param:
        return os.path.abspath(os.path.expanduser(db_param))

    script_dir = os.path.dirname(os.path.abspath(__file__))
    try:
        res = subprocess.run(
            ["git", "rev-parse", "--git-path", DB_NAME],
            cwd=script_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            check=True,
        )
        git_db = res.stdout.strip()
        if git_db:
            if not os.path.isabs(git_db):
                return os.path.abspath(os.path.join(script_dir, git_db))
            return os.path.abspath(git_db)
    except Exception:
        pass

    return os.path.abspath(os.path.join(script_dir, DB_NAME))


def resolve_ignored_path(ignored_param: Optional[str] = None) -> str:
    """Resolves default target path for local ignored file saving."""
    if ignored_param:
        return os.path.abspath(os.path.expanduser(ignored_param))

    script_dir = os.path.dirname(os.path.abspath(__file__))
    script_ignored = os.path.join(script_dir, IGNORED_NAME)
    if os.path.exists(script_ignored):
        return script_ignored

    return os.path.abspath(IGNORED_NAME)


def get_db_connection(db_path: str) -> sqlite3.Connection:
    """Returns a SQLite connection with busy_timeout configured for concurrency."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA busy_timeout = 5000;")
    return conn


def load_ignored_shas(
    repo_path: str,
    ignored_param: Optional[str] = None,
) -> Tuple[Set[str], str]:
    """
    Loads ignored commit SHAs from either origin/scripts branch or local file,
    whichever is newer, WITHOUT modifying the local file on disk.
    Returns (set_of_shas, local_save_path).
    """
    local_path = resolve_ignored_path(ignored_param)
    local_ts = int(os.path.getmtime(local_path)) if os.path.exists(local_path) else 0

    remote_shas: Optional[Set[str]] = None
    remote_ts = 0

    if os.path.exists(repo_path):
        candidate_paths = [
            "scripts/alt-commits/alt-commits-ignored.txt",
            "scripts/alt_commit/alt-commits-ignored.txt",
            "alt-commits-ignored.txt",
        ]
        for rel_path in candidate_paths:
            try:
                subprocess.run(
                    ["git", "cat-file", "-e", f"origin/scripts:{rel_path}"],
                    cwd=target_repo,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=True,
                )
                res_time = subprocess.run(
                    ["git", "log", "-1", "--format=%at", "origin/scripts", "--", rel_path],
                    cwd=target_repo,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    universal_newlines=True,
                    check=True,
                )
                ts_str = res_time.stdout.strip()
                if ts_str.isdigit():
                    remote_ts = int(ts_str)
                    if remote_ts > local_ts:
                        res_show = subprocess.run(
                            ["git", "show", f"origin/scripts:{rel_path}"],
                            cwd=target_repo,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            universal_newlines=True,
                            errors="replace",
                            check=True,
                        )
                        remote_shas = set()
                        for line in res_show.stdout.splitlines():
                            s = line.strip().lower()
                            if s and not s.startswith("#"):
                                remote_shas.add(s)
                break
            except Exception:
                continue

    if remote_shas is not None and remote_ts > local_ts:
        return remote_shas, local_path

    shas = set()
    if os.path.exists(local_path):
        try:
            with open(local_path, "r") as f:
                for line in f:
                    s = line.strip().lower()
                    if s and not s.startswith("#"):
                        shas.add(s)
        except Exception as e:
            sys.stderr.write(f"Warning: Failed to load ignored file '{local_path}': {e}\n")

    return shas, local_path


def save_ignored_shas(ignored_path: str, shas: Set[str]) -> None:
    """Persists updated ignored SHAs to disk."""
    try:
        os.makedirs(os.path.dirname(os.path.abspath(ignored_path)), exist_ok=True)
        with open(ignored_path, "w") as f:
            for sha in sorted(shas):
                f.write(f"{sha}\n")
    except Exception as e:
        sys.stderr.write(f"Error: Failed to save ignored list to '{ignored_path}': {e}\n")


def check_ignored_up_to_date(ignored_param: Optional[str] = None) -> None:
    """
    Runs git fetch in the script's repository (kernel-source), then ensures tools
    cannot run if origin/scripts has a newer version of the ignored file than the local file.
    Aborts if git fetch fails.
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    target_repo = script_dir

    if not os.path.exists(target_repo):
        sys.stderr.write(f"Error: Target repository '{target_repo}' does not exist.\n")
        sys.exit(1)

    print(f"Running 'git fetch' in {target_repo}...", flush=True)
    try:
        res_fetch = subprocess.run(
            ["git", "fetch"],
            cwd=target_repo,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
        )
        if res_fetch.returncode != 0:
            err_msg = res_fetch.stderr.strip() or "git fetch failed"
            sys.stderr.write(f"Error: 'git fetch' failed in {target_repo}:\n{err_msg}\n")
            sys.exit(1)
    except Exception as e:
        sys.stderr.write(f"Error: Failed to execute 'git fetch': {e}\n")
        sys.exit(1)

    local_path = resolve_ignored_path(ignored_param)
    local_ts = int(os.path.getmtime(local_path)) if os.path.exists(local_path) else 0

    candidate_paths = [
        "scripts/alt-commits/alt-commits-ignored.txt",
        "scripts/alt_commit/alt-commits-ignored.txt",
        "alt-commits-ignored.txt",
    ]
    for rel_path in candidate_paths:
        try:
            subprocess.run(
                ["git", "cat-file", "-e", f"origin/scripts:{rel_path}"],
                cwd=target_repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            )
            res_time = subprocess.run(
                ["git", "log", "-1", "--format=%at", "origin/scripts", "--", rel_path],
                cwd=target_repo,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True,
                check=True,
            )
            ts_str = res_time.stdout.strip()
            if ts_str.isdigit():
                remote_ts = int(ts_str)
                if remote_ts > local_ts:
                    sys.stderr.write(
                        f"Error: The remote ignored file 'origin/scripts:{rel_path}' is newer than the local file '{local_path}'.\n"
                        "Please update your local file from the origin/scripts branch before running alt-browser.\n"
                    )
                    sys.exit(1)
            break
        except Exception:
            continue


class FileLock:
    """Non-blocking process file lock using fcntl."""

    def __init__(self, lock_path: str):
        self.lock_path = lock_path
        self.file_obj: Optional[TextIO] = None

    def acquire(self, blocking: bool = False) -> bool:
        try:
            os.makedirs(os.path.dirname(os.path.abspath(self.lock_path)), exist_ok=True)
            self.file_obj = open(self.lock_path, "a+")
            flags = fcntl.LOCK_EX
            if not blocking:
                flags |= fcntl.LOCK_NB
            fcntl.flock(self.file_obj, flags)
            return True
        except (IOError, OSError):
            if self.file_obj:
                try:
                    self.file_obj.close()
                except Exception:
                    pass
                self.file_obj = None
            return False

    def release(self) -> None:
        if self.file_obj:
            try:
                fcntl.flock(self.file_obj, fcntl.LOCK_UN)
                self.file_obj.close()
            except Exception:
                pass
            self.file_obj = None
