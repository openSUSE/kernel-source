#!/usr/bin/python3
# -*- coding: utf-8 -*-


from pathlib import Path
import subprocess
import tempfile
import unittest
import shutil
import sys
import os

import tests.support  # before git_sort
from git_sort import pygit2_wrapper as pygit2
from git_sort import series_conf
from git_sort import git_sort
from git_sort import lib


class TestMergeTool(unittest.TestCase):
    def setUp(self):
        os.environ["XDG_CACHE_HOME"] = tempfile.mkdtemp(prefix="gs_cache")

        # setup stub linux repository
        os.environ["LINUX_GIT"] = tempfile.mkdtemp(prefix="gs_repo")
        self.repo = pygit2.init_repository(os.environ["LINUX_GIT"])

        author = pygit2.Signature("Alice Author", "alice@authors.tld")
        committer = pygit2.Signature("Cecil Committer", "cecil@committers.tld")
        tree = self.repo.TreeBuilder()

        k_org_canon_prefix = "git://git.kernel.org/pub/scm/linux/kernel/git/"
        self.mainline_repo = k_org_canon_prefix + "torvalds/linux.git"
        self.repo.remotes.create("origin", self.mainline_repo)

        self.commits = {}
        self.commits["mainline 0"] = self.repo.create_commit(
            "refs/heads/mainline",
            author,
            committer,
            "mainline 0\n\nlog",
            tree.write(),
            []
        )

        self.commits["mainline 1"] = self.repo.create_commit(
            "refs/heads/mainline",
            author,
            committer,
            "mainline 1\n\nlog",
            tree.write(),
            [self.commits["mainline 0"]]
        )

        self.commits["mainline 2"] = self.repo.create_commit(
            "refs/heads/mainline",
            author,
            committer,
            "mainline 2\n\nlog",
            tree.write(),
            [self.commits["mainline 1"]]
        )
        self.repo.references.create("refs/remotes/origin/master",
                                    self.commits["mainline 2"])

        self.repo.checkout("refs/heads/mainline")

        # setup stub kernel-source content
        self.ks_dir = Path(tempfile.mkdtemp(prefix="gs_ks"))

        pygit2.init_repository(self.ks_dir)
        subprocess.check_call(
            ("git", "config", "--add", "mergetool.git-sort.cmd",
             "%s $LOCAL $BASE $REMOTE $MERGED" % (
                 lib.bindir / 'series_merge_tool',),), cwd=self.ks_dir)
        subprocess.check_call(("git", "config", "--add",
                               "mergetool.git-sort.trustexitcode", "true",), cwd=self.ks_dir)

        self.patch_dir = self.ks_dir / 'patches.suse'
        self.patch_dir.mkdir()


    def tearDown(self):
        shutil.rmtree(os.environ["XDG_CACHE_HOME"])
        shutil.rmtree(os.environ["LINUX_GIT"])
        shutil.rmtree(self.ks_dir)


    def test_moved(self):
        names = {}

        # local branch
        names["mainline 0"] = tests.support.format_patch(
            self.repo.get(self.commits["mainline 0"]), mainline="v0",
            directory=self.patch_dir)
        names["mainline 1"] = tests.support.format_patch(
            self.repo.get(self.commits["mainline 1"]),
            directory=self.patch_dir)

        (self.ks_dir / 'series.conf').write_text(
            tests.support.format_series((
                (None, (
                    names["mainline 0"],
                )),
                ("out-of-tree patches", (
                    names["mainline 1"],
                )),
            )))

        subprocess.check_call(("git", "add", "series.conf", "patches.suse",),
                              cwd=self.ks_dir, stdout=subprocess.DEVNULL)
        subprocess.check_call(("git", "commit", "-m", "mainline 0",),
                              cwd=self.ks_dir, stdout=subprocess.DEVNULL)

        names["mainline 2"] = tests.support.format_patch(
            self.repo.get(self.commits["mainline 2"]), mainline="v0",
            directory=self.patch_dir)

        (self.ks_dir / 'series.conf').write_text(
            tests.support.format_series((
                (None, (
                    names["mainline 0"],
                    names["mainline 2"],
                )),
                ("out-of-tree patches", (
                    names["mainline 1"],
                )),
            )))

        subprocess.check_call(("git", "add", "series.conf", "patches.suse",),
                              cwd=self.ks_dir, stdout=subprocess.DEVNULL)
        subprocess.check_call(("git", "commit", "-m", "mainline 2",),
                              cwd=self.ks_dir, stdout=subprocess.DEVNULL)

        # remote branch
        subprocess.check_call(("git", "checkout", "-q", "-b", "other",
                               "HEAD^",), cwd=self.ks_dir)
        names["mainline 1"] = tests.support.format_patch(
            self.repo.get(self.commits["mainline 1"]), mainline="v0",
            directory=self.patch_dir)

        (self.ks_dir / 'series.conf').write_text(
            tests.support.format_series((
                (None, (
                    names["mainline 0"],
                    names["mainline 1"],
                )),
            )))

        subprocess.check_call(("git", "add", "series.conf", "patches.suse",),
                              cwd=self.ks_dir, stdout=subprocess.DEVNULL)
        subprocess.check_call(("git", "commit", "-m", "Refresh mainline 1",),
                              cwd=self.ks_dir, stdout=subprocess.DEVNULL)

        # test merge_tool.py
        subprocess.check_call(("git", "checkout", "-q", "master",), cwd=self.ks_dir)
        retval = subprocess.call(("git", "merge", "other",), cwd=self.ks_dir,
                                       stdout=subprocess.DEVNULL,
                                       stderr=subprocess.DEVNULL)
        self.assertEqual(retval, 1)
        #sys.stdin.readline()
        retval = subprocess.check_output(
            ("git", "mergetool", "--tool=git-sort", "series.conf",), cwd=self.ks_dir,
            stdin=subprocess.DEVNULL)
        self.assertEqual(
            "1 commits changed section from base to remote.",
            retval.decode().splitlines()[-1].strip())
        self.assertEqual(
                tests.support.format_series((
                    (None, (
                        names["mainline 0"],
                        names["mainline 1"],
                        names["mainline 2"],
                    )),
                )),
                (self.ks_dir / 'series.conf').read_text())
        retval = subprocess.check_output(("git", "status", "--porcelain",
                                          "series.conf",), cwd=self.ks_dir)
        self.assertEqual(retval.decode().strip(), "M  series.conf")
