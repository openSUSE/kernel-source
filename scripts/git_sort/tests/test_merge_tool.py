#!/usr/bin/python3
# -*- coding: utf-8 -*-

import os
import os.path
import shutil
import subprocess
import sys
import tempfile
import unittest

import pygit2_wrapper as pygit2

from pathlib import Path
os.environ['GIT_SORT_REPOSITORIES'] = str(Path(__file__).parent / 'git_sort.yaml')

import git_sort
import lib
import series_conf
import tests.support


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
        self.ks_dir = tempfile.mkdtemp(prefix="gs_ks")
        os.chdir(self.ks_dir)

        pygit2.init_repository("./")
        subprocess.check_call(
            ("git", "config", "--add", "mergetool.git-sort.cmd",
             "%s $LOCAL $BASE $REMOTE $MERGED" % (
                 os.path.join(lib.libdir(), "merge_tool.py"),),))
        subprocess.check_call(("git", "config", "--add",
                               "mergetool.git-sort.trustexitcode", "true",))

        self.patch_dir = "patches.suse"
        os.mkdir(self.patch_dir)


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

        with open("series.conf", mode="w") as f:
            f.write(tests.support.format_series((
                (None, (
                    names["mainline 0"],
                )),
                ("out-of-tree patches", (
                    names["mainline 1"],
                )),
            )))

        subprocess.check_call(("git", "add", "series.conf", "patches.suse",),
                              stdout=subprocess.DEVNULL)
        subprocess.check_call(("git", "commit", "-m", "mainline 0",),
                              stdout=subprocess.DEVNULL)

        names["mainline 2"] = tests.support.format_patch(
            self.repo.get(self.commits["mainline 2"]), mainline="v0",
            directory=self.patch_dir)

        with open("series.conf", mode="w") as f:
            f.write(tests.support.format_series((
                (None, (
                    names["mainline 0"],
                    names["mainline 2"],
                )),
                ("out-of-tree patches", (
                    names["mainline 1"],
                )),
            )))

        subprocess.check_call(("git", "add", "series.conf", "patches.suse",),
                              stdout=subprocess.DEVNULL)
        subprocess.check_call(("git", "commit", "-m", "mainline 2",),
                              stdout=subprocess.DEVNULL)

        # remote branch
        subprocess.check_call(("git", "checkout", "-q", "-b", "other",
                               "HEAD^",))
        names["mainline 1"] = tests.support.format_patch(
            self.repo.get(self.commits["mainline 1"]), mainline="v0",
            directory=self.patch_dir)

        with open("series.conf", mode="w") as f:
            f.write(tests.support.format_series((
                (None, (
                    names["mainline 0"],
                    names["mainline 1"],
                )),
            )))

        subprocess.check_call(("git", "add", "series.conf", "patches.suse",),
                              stdout=subprocess.DEVNULL)
        subprocess.check_call(("git", "commit", "-m", "Refresh mainline 1",),
                              stdout=subprocess.DEVNULL)

        # test merge_tool.py
        subprocess.check_call(("git", "checkout", "-q", "master",))
        retval = subprocess.call(("git", "merge", "other",),
                                       stdout=subprocess.DEVNULL,
                                       stderr=subprocess.DEVNULL)
        self.assertEqual(retval, 1)
        #sys.stdin.readline()
        retval = subprocess.check_output(
            ("git", "mergetool", "--tool=git-sort", "series.conf",),
            stdin=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.assertEqual(
            "1 commits changed section from base to remote.",
            retval.decode().splitlines()[-1].strip())
        with open("series.conf") as f:
            self.assertEqual(
                tests.support.format_series((
                    (None, (
                        names["mainline 0"],
                        names["mainline 1"],
                        names["mainline 2"],
                    )),
                )),
                f.read())
        retval = subprocess.check_output(("git", "status", "--porcelain",
                                          "series.conf",))
        self.assertEqual(retval.decode().strip(), "M  series.conf")
