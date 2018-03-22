#!/usr/bin/python
# -*- coding: utf-8 -*-

from __future__ import print_function

import os
import pygit2
import shutil
import subprocess
import tempfile
import unittest
import sys

import git_sort
import lib
import tests.support


class TestSeriesInsert(unittest.TestCase):
    def setUp(self):
        os.environ["XDG_CACHE_HOME"] = tempfile.mkdtemp(prefix="gs_cache")

        # setup stub linux repository
        os.environ["LINUX_GIT"] = tempfile.mkdtemp(prefix="gs_repo")
        self.repo = pygit2.init_repository(os.environ["LINUX_GIT"])

        author = pygit2.Signature('Alice Author', 'alice@authors.tld')
        committer = pygit2.Signature('Cecil Committer', 'cecil@committers.tld')
        tree = self.repo.TreeBuilder().write()

        parent = []
        commits = []
        for i in range(3):
            subject = "mainline %d" % (i,)
            cid = self.repo.create_commit(
                "refs/heads/master",
                author,
                committer,
                "%s\n\nlog" % (subject,),
                tree,
                parent
            )
            parent = [cid]
            commits.append(cid)
        self.commits = commits

        self.repo.remotes.create(
            "origin",
            "git://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git")
        self.repo.references.create("refs/remotes/origin/master", commits[-1])

        self.index = git_sort.SortIndex(self.repo)

        # setup stub kernel-source content
        self.ks_dir = tempfile.mkdtemp(prefix="gs_ks")
        patch_dir = os.path.join(self.ks_dir, "patches.suse")
        os.mkdir(patch_dir)
        os.chdir(patch_dir)
        for commit in commits:
            tests.support.format_patch(self.repo.get(commit),
                                       mainline="v3.45-rc6")

    def tearDown(self):
        shutil.rmtree(os.environ["XDG_CACHE_HOME"])
        shutil.rmtree(os.environ["LINUX_GIT"])
        shutil.rmtree(self.ks_dir)


    def test_simple(self):
        si_path = os.path.join(lib.libdir(), "series_insert.py")
        os.chdir(self.ks_dir)

        series = "series.conf"
        open(series, mode="w").write(
"""########################################################
	# sorted patches
	########################################################
	patches.suse/mainline-0.patch
	patches.suse/mainline-2.patch
	########################################################
	# end of sorted patches
	########################################################
""")

        subprocess.check_call([si_path, "patches.suse/mainline-1.patch"])
        self.assertEqual(open(series).read(),
"""########################################################
	# sorted patches
	########################################################
	patches.suse/mainline-0.patch
	patches.suse/mainline-1.patch
	patches.suse/mainline-2.patch
	########################################################
	# end of sorted patches
	########################################################
""")

        content = []
        with open("patches.suse/mainline-1.patch") as f:
            for line in f:
                if line.startswith("Git-commit: "):
                    line = "Git-commit: invalid\n"
                content.append(line)
        open("patches.suse/mainline-1.patch", mode="w+").writelines(content)

        open(series, mode="w").write(
"""########################################################
	# sorted patches
	########################################################
	patches.suse/mainline-0.patch
	patches.suse/mainline-2.patch
	########################################################
	# end of sorted patches
	########################################################
""")

        try:
            subprocess.check_output([si_path, "patches.suse/mainline-1.patch"],
                                   stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError as err:
            self.assertEqual(err.returncode, 1)
            self.assertEqual(
                err.output,
                "Error: Git-commit tag \"invalid\" in patch "
                "\"patches.suse/mainline-1.patch\" is not a valid revision.\n")
        else:
            self.assertTrue(False)

        os.unlink(series)


if __name__ == '__main__':
    # Run a single testcase
    suite = unittest.TestLoader().loadTestsFromTestCase(TestSeriesInsert)
    unittest.TextTestRunner(verbosity=2).run(suite)
