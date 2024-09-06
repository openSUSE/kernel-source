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
from git_sort import git_sort
from git_sort import lib


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
        self.ks_dir = Path(tempfile.mkdtemp(prefix="gs_ks"))
        patch_dir = self.ks_dir / 'patches.suse'
        patch_dir.mkdir()
        for commit in commits:
            tests.support.format_patch(self.repo.get(commit),
                                       directory=patch_dir,
                                       mainline="v3.45-rc6")
        series = self.ks_dir / 'series.conf'
        content = tests.support.format_series((
            (None,
             ("patches.suse/mainline-%d.patch" % (i,) for i in (0, 2,))),
        ))
        series.write_text(content)

    def tearDown(self):
        shutil.rmtree(os.environ["XDG_CACHE_HOME"])
        shutil.rmtree(os.environ["LINUX_GIT"])
        shutil.rmtree(self.ks_dir)


    def test_simple(self):

        series = self.ks_dir / 'series.conf'

        subprocess.check_call([lib.si_path, 'patches.suse/mainline-1.patch'], cwd=self.ks_dir)
        content = series.read_text()
        self.assertEqual(content,
            tests.support.format_series((
                (None,
                 ("patches.suse/mainline-%d.patch" % (i,) for i in range(3))),
            )))

    def test_invalid(self):

        content = []
        with (self.ks_dir / 'patches.suse/mainline-1.patch').open() as f:
            for line in f:
                if line.startswith("Git-commit: "):
                    line = "Git-commit: invalid\n"
                content.append(line)
        with (self.ks_dir / 'patches.suse/mainline-1.patch').open('w') as f:
            f.writelines(content)

        try:
            subprocess.check_output([lib.si_path, 'patches.suse/mainline-1.patch'],
                                   cwd=self.ks_dir, stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError as err:
            self.assertEqual(err.returncode, 1)
            self.assertEqual(
                err.output.decode(),
                "Error: Git-commit tag \"invalid\" in patch "
                "\"patches.suse/mainline-1.patch\" is not a valid revision.\n")
        else:
            self.assertTrue(False)

    def test_noheader(self):

        content = []
        with (self.ks_dir / 'patches.suse/mainline-1.patch').open() as f:
            for line in f:
                if not line.startswith("Git-commit: ") and not line.startswith("Patch-mainline: "):
                    content.append(line)
        with (self.ks_dir / 'patches.suse/mainline-1.patch').open('w') as f:
            f.writelines(content)

        try:
            subprocess.check_output([lib.si_path, 'patches.suse/mainline-1.patch'],
                                   cwd=self.ks_dir, stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError as err:
            self.assertEqual(err.returncode, 1)
            self.assertEqual(
                err.output.decode(),
                'Error: There is a problem with patch "patches.suse/mainline-1.patch". '
                'The Patch-mainline tag is missing.\n')
        else:
            self.assertTrue(False)


if __name__ == '__main__':
    # Run a single testcase
    suite = unittest.TestLoader().loadTestsFromTestCase(TestSeriesInsert)
    unittest.TextTestRunner(verbosity=2).run(suite)
