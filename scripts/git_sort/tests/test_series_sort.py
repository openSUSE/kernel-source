#!/usr/bin/python
# -*- coding: utf-8 -*-

from __future__ import print_function

import collections
import os
import os.path
import pygit2
import shelve
import shutil
import subprocess
import sys
import tempfile
import unittest

import git_sort
import lib


def write_patch(name, mainline=None, repo=None, commit=None):
    f = open(name, mode="w")
    if mainline and commit and repo is None:
        f.write("Patch-mainline: %s\n" % (mainline,))
        f.write("Git-commit: %s\n" % (commit,))
    elif mainline is None and repo and commit:
        f.write("Patch-mainline: Queued in subsystem maintainer repository\n")
        f.write("Git-repo: %s\n" % (repo,))
        f.write("Git-commit: %s\n" % (commit,))
    elif mainline and repo is None and commit is None:
        f.write("Patch-mainline: %s\n" % (mainline,))
    else:
        assert False


class TestSeriesSort(unittest.TestCase):
    def setUp(self):
        os.environ["XDG_CACHE_HOME"] = tempfile.mkdtemp(prefix="gs_cache")

        # setup stub linux repository
        os.environ["LINUX_GIT"] = tempfile.mkdtemp(prefix="gs_repo")
        self.repo = pygit2.init_repository(os.environ["LINUX_GIT"])

        author = pygit2.Signature('Alice Author', 'alice@authors.tld')
        committer = pygit2.Signature('Cecil Committer', 'cecil@committers.tld')
        tree = self.repo.TreeBuilder().write()

        m0 = self.repo.create_commit(
            "refs/heads/mainline",
            author,
            committer,
            "mainline 0\n\nlog",
            tree,
            []
        )

        n0 = self.repo.create_commit(
            "refs/heads/net",
            author,
            committer,
            "net 0\n\nlog",
            tree,
            [m0]
        )

        self.repo.checkout("refs/heads/mainline")
        m1 = self.repo.create_commit(
            "refs/heads/mainline",
            author,
            committer,
            "mainline 1, merge net\n\nlog",
            tree,
            [m0, n0]
        )

        m2 = self.repo.create_commit(
            "refs/heads/mainline",
            author,
            committer,
            "mainline 2\n\nlog",
            tree,
            [m1]
        )

        n1 = self.repo.create_commit(
            "refs/heads/net",
            author,
            committer,
            "net 1\n\nlog",
            tree,
            [n0]
        )

        n2 = self.repo.create_commit(
            "refs/heads/net",
            author,
            committer,
            "net 2\n\nlog",
            tree,
            [n1]
        )

        self.repo.remotes.create("origin",
                                 "git://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git")
        self.repo.references.create("refs/remotes/origin/master", m2)

        self.repo.remotes.create("net",
                                 "git://git.kernel.org/pub/scm/linux/kernel/git/davem/net.git")
        self.repo.references.create("refs/remotes/net/master", n2)

        self.index = git_sort.SortIndex(self.repo)

        # setup stub kernel-source content
        self.ks_dir = tempfile.mkdtemp(prefix="gs_ks")
        k_org_canon_prefix = "git://git.kernel.org/pub/scm/linux/kernel/git/"
        patch_dir = os.path.join(self.ks_dir, "patches.suse")
        os.mkdir(patch_dir)
        os.chdir(patch_dir)
        write_patch("mainline0.patch", mainline="v3.45-rc6", commit=str(m0))
        write_patch("net0.patch", mainline="v3.45-rc6", commit=str(n0))
        write_patch("net1.patch", repo=k_org_canon_prefix + "davem/net.git",
                    commit=str(n1))
        write_patch("net2.patch", repo=k_org_canon_prefix + "davem/net.git",
                    commit=str(n2))
        write_patch("net2.patch", repo=k_org_canon_prefix + "davem/net.git",
                    commit=str(n2))
        write_patch("oot0.patch", mainline="no")
        write_patch("oot1.patch", mainline="no")

    def tearDown(self):
        shutil.rmtree(os.environ["XDG_CACHE_HOME"])
        shutil.rmtree(os.environ["LINUX_GIT"])
        shutil.rmtree(self.ks_dir)


    def test_absent(self):
        ss_path = os.path.join(lib.libdir(), "series_sort.py")
        os.chdir(self.ks_dir)

        (tmp, series,) = tempfile.mkstemp(dir=self.ks_dir)
        open(series, mode="w").write(
"""
	patches.suse/unsorted-before.patch
""")

        try:
            output = subprocess.check_output([ss_path, series],
                                             stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError as err:
            self.assertEqual(err.output, "Error: Sorted subseries not found.\n")
        else:
            self.assertTrue(False)

        os.unlink(series)


    def test_sort_small(self):
        ss_path = os.path.join(lib.libdir(), "series_sort.py")
        os.chdir(self.ks_dir)

        (tmp, series,) = tempfile.mkstemp(dir=self.ks_dir)
        open(series, mode="w").write(
"""########################################################
	# sorted patches
	########################################################
	patches.suse/mainline0.patch
	patches.suse/net0.patch
	########################################################
	# end of sorted patches
	########################################################
""")

        subprocess.check_call([ss_path, "-c", series])
        content = open(series).read()
        output = subprocess.check_call([ss_path, series])
        self.assertEqual(open(series).read(), content)

        os.unlink(series)


    def test_sort(self):
        ss_path = os.path.join(lib.libdir(), "series_sort.py")
        os.chdir(self.ks_dir)

        (tmp, series,) = tempfile.mkstemp(dir=self.ks_dir)
        open(series, mode="w").write(
"""
	patches.suse/unsorted-before.patch

	########################################################
	# sorted patches
	########################################################
	patches.suse/mainline0.patch
	patches.suse/net0.patch

	# davem/net
	patches.suse/net1.patch
	patches.suse/net2.patch

	# out-of-tree patches
	patches.suse/oot0.patch
	patches.suse/oot1.patch

	########################################################
	# end of sorted patches
	########################################################

	patches.suse/unsorted-after.patch
""")

        subprocess.check_call([ss_path, "-c", series])
        content = open(series).read()
        output = subprocess.check_call([ss_path, series])
        self.assertEqual(open(series).read(), content)

        os.unlink(series)


if __name__ == '__main__':
    # Run a single testcase
    suite = unittest.TestLoader().loadTestsFromTestCase(TestSeriesSort)
    unittest.TextTestRunner(verbosity=2).run(suite)
