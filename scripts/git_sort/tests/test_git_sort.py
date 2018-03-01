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


class TestRepoURL(unittest.TestCase):
    def test_eq(self):
        self.assertEqual(
            git_sort.RepoURL("git://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git"),
            git_sort.RepoURL("git://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git")
        )

        self.assertEqual(
            git_sort.RepoURL("git://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux-2.6.git"),
            git_sort.RepoURL("git://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git")
        )

        self.assertEqual(
            git_sort.RepoURL("git://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git"),
            git_sort.RepoURL("http://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git")
        )

        self.assertNotEqual(
            git_sort.RepoURL("git://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git"),
            git_sort.RepoURL("git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git")
        )

        self.assertEqual(
            git_sort.RepoURL("git://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git"),
            git_sort.RepoURL("git://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux")
        )

        self.assertEqual(
            git_sort.RepoURL("git://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git"),
            git_sort.RepoURL("torvalds/linux.git")
        )

        self.assertEqual(
            git_sort.RepoURL("torvalds/linux.git"),
            git_sort.RepoURL("torvalds/linux")
        )

        self.assertNotEqual(
            git_sort.RepoURL("torvalds/linux.git"),
            git_sort.RepoURL("davem/net.git")
        )


    def test_repr(self):
        url_canon = "git://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git"
        url_non_canon = "git://linuxtv.org/media_tree.git"

        self.assertEqual(
            repr(git_sort.RepoURL(url_canon)),
            url_canon
        )

        self.assertEqual(
            str(git_sort.RepoURL(url_canon)),
            "torvalds/linux"
        )

        self.assertEqual(
            repr(git_sort.RepoURL(url_non_canon)),
            url_non_canon
        )

        self.assertEqual(
            str(git_sort.RepoURL(url_non_canon)),
            url_non_canon
        )

        self.assertEqual(
            str(git_sort.RepoURL(None)),
            ""
        )


class TestHead(unittest.TestCase):
    def test_eq(self):
        self.assertEqual(
            git_sort.Head(git_sort.RepoURL("torvalds/linux.git")),
            git_sort.Head(git_sort.RepoURL("torvalds/linux.git")),
        )

        self.assertEqual(
            git_sort.Head(git_sort.RepoURL("torvalds/linux.git")),
            git_sort.Head(git_sort.RepoURL("torvalds/linux.git"), "master"),
        )

        self.assertNotEqual(
            git_sort.Head(git_sort.RepoURL("torvalds/linux.git")),
            git_sort.Head(git_sort.RepoURL("davem/net.git")),
        )

        self.assertTrue(
            git_sort.Head(git_sort.RepoURL("torvalds/linux.git")) <
            git_sort.Head(git_sort.RepoURL("davem/net.git"))
        )


class TestIndex(unittest.TestCase):
    def setUp(self):
        os.environ["XDG_CACHE_HOME"] = tempfile.mkdtemp(prefix="gs_cache")
        self.repo_dir = tempfile.mkdtemp(prefix="gs_repo")
        self.repo = pygit2.init_repository(self.repo_dir)

        author = pygit2.Signature('Alice Author', 'alice@authors.tld')
        committer = pygit2.Signature('Cecil Committer', 'cecil@committers.tld')
        tree = self.repo.TreeBuilder().write()

        parent = []
        commits = []
        for i in range(3):
            subject = "commit %d" % (i,)
            cid = self.repo.create_commit(
                "refs/heads/master",
                author,
                committer,
                "%s\n\nlog" % (subject,),
                tree,
                parent
            )
            parent = [cid]
            commits.append((str(cid), subject,))
        self.commits = commits

        self.index = git_sort.SortIndex(self.repo)


    def tearDown(self):
        shutil.rmtree(os.environ["XDG_CACHE_HOME"])
        shutil.rmtree(self.repo_dir)


    def test_heads(self):
        self.assertEqual(
            git_sort.get_heads(self.repo),
            collections.OrderedDict([
                (git_sort.Head(git_sort.RepoURL(None), "HEAD"),
                 str(self.commits[-1][0]),)])
        )


    def test_sort(self):
        mapping = {commit : subject for commit, subject in self.commits}
        r = self.index.sort(mapping)
        self.assertEqual(
            len(mapping),
            0
        )
        self.assertEqual(
            len(r),
            1
        )
        r2 = r.items()[0]
        self.assertEqual(
            r2[0],
            git_sort.Head(git_sort.RepoURL(None), "HEAD")
        )
        self.assertEqual(
            r2[1],
            [subject for commit, subject in self.commits]
        )


class TestIndexLinux(unittest.TestCase):
    def setUp(self):
        os.environ["XDG_CACHE_HOME"] = tempfile.mkdtemp(prefix="gs_cache")
        self.repo_dir = tempfile.mkdtemp(prefix="gs_repo")
        self.repo = pygit2.init_repository(self.repo_dir)

        author = pygit2.Signature('Alice Author', 'alice@authors.tld')
        committer = pygit2.Signature('Cecil Committer', 'cecil@committers.tld')
        tree = self.repo.TreeBuilder().write()

        self.commits = []
        m0 = self.repo.create_commit(
            "refs/heads/mainline",
            author,
            committer,
            "mainline 0\n\nlog",
            tree,
            []
        )
        self.commits.append(self.repo.get(m0))
        self.repo.create_reference_direct("refs/tags/v4.8", m0, False)
        self.repo.create_tag("v4.9", m0, pygit2.GIT_REF_OID, committer,
                             "Linux 4.9")

        n0 = self.repo.create_commit(
            "refs/heads/net",
            author,
            committer,
            "net 0\n\nlog",
            tree,
            [m0]
        )
        self.commits.append(self.repo.get(n0))

        self.repo.checkout("refs/heads/mainline")

        m1 = self.repo.create_commit(
            "refs/heads/mainline",
            author,
            committer,
            "mainline 1, merge net\n\nlog",
            tree,
            [m0, n0]
        )
        self.repo.create_tag("v4.10", m1, pygit2.GIT_REF_OID, committer,
                             "Linux 4.10")

        self.repo.remotes.create("origin",
                                 "git://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git")
        self.repo.references.create("refs/remotes/origin/master", m1)

        self.repo.remotes.create("net",
                                 "git://git.kernel.org/pub/scm/linux/kernel/git/davem/net.git")
        self.repo.references.create("refs/remotes/net/master", n0)

        self.heads = {"mainline" : str(m1),
                      "net" : str(n0)}
        self.index = git_sort.SortIndex(self.repo)

        #sys.stdin.readline()


    def tearDown(self):
        shutil.rmtree(os.environ["XDG_CACHE_HOME"])
        shutil.rmtree(self.repo_dir)


    def test_heads(self):
        self.assertEqual(
            git_sort.get_heads(self.repo),
            collections.OrderedDict([
                (git_sort.Head(git_sort.RepoURL("torvalds/linux.git")),
                 self.heads["mainline"]),
                (git_sort.Head(git_sort.RepoURL("davem/net.git")),
                 self.heads["net"]),
            ])
        )


    def test_sort(self):
        mapping = {str(commit.id) : commit.message for commit in self.commits}
        r = self.index.sort(mapping)
        self.assertEqual(
            len(mapping),
            0
        )
        self.assertEqual(
            len(r),
            2
        )
        r2 = r.items()[0]
        self.assertEqual(
            r2[0],
            git_sort.Head(git_sort.RepoURL("torvalds/linux.git"))
        )
        self.assertEqual(
            r2[1],
            [commit.message for commit in self.commits]
        )


    def test_describe(self):
        self.assertEqual(
            self.index.describe(self.index.lookup(str(self.commits[1].id))[1]),
            "v4.10")


class TestCache(unittest.TestCase):
    def setUp(self):
        os.environ["XDG_CACHE_HOME"] = tempfile.mkdtemp(prefix="gs_cache")
        self.repo_dir = tempfile.mkdtemp(prefix="gs_repo")
        self.repo = pygit2.init_repository(self.repo_dir)

        author = pygit2.Signature('Alice Author', 'alice@authors.tld')
        committer = pygit2.Signature('Cecil Committer', 'cecil@committers.tld')
        tree = self.repo.TreeBuilder().write()

        parent = []
        commits = []
        for i in range(3):
            subject = "commit %d" % (i,)
            cid = self.repo.create_commit(
                "refs/heads/master",
                author,
                committer,
                "%s\n\nlog" % (subject,),
                tree,
                parent
            )
            parent = [cid]
            commits.append("%s %s" % (str(cid), subject,))
        self.commits = commits


    def tearDown(self):
        shutil.rmtree(os.environ["XDG_CACHE_HOME"])
        shutil.rmtree(self.repo_dir)


    def test_cache(self):
        gs_path = os.path.join(lib.libdir(), "git_sort.py")
        cache_path = os.path.join(os.environ["XDG_CACHE_HOME"], "git-sort")

        input_text = "\n".join(self.commits)

        os.chdir(self.repo_dir)
        output = subprocess.check_output([gs_path, "-d"]).splitlines()
        self.assertEqual(output[-1], "Will rebuild history")

        # "-d" should not create a cache
        retval = 0
        try:
            os.stat(cache_path)
        except OSError as e:
            retval = e.errno
        self.assertEqual(retval, 2)

        sp = subprocess.Popen(gs_path,
                              stdin=subprocess.PIPE,
                              stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE)
        output_ref, err = sp.communicate(input_text)
        time1 = os.stat(cache_path).st_mtime

        output = subprocess.check_output([gs_path, "-d"]).splitlines()
        self.assertEqual(output[-1], "Will not rebuild history")

        # "-d" should not modify a cache
        self.assertEqual(os.stat(cache_path).st_mtime, time1)

        # test that git-sort action is the same as "-d" states (no cache
        # rebuild)
        sp = subprocess.Popen(gs_path,
                              stdin=subprocess.PIPE,
                              stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE)
        output, err = sp.communicate(input_text)
        self.assertEqual(output, output_ref)
        self.assertEqual(os.stat(cache_path).st_mtime, time1)

        # test version number change
        shelve.open(cache_path)["version"] = 1
        output = subprocess.check_output([gs_path, "-d"]).splitlines()
        self.assertEqual(output[1], "Unsupported cache version")
        self.assertEqual(output[-1], "Will rebuild history")

        sp = subprocess.Popen(gs_path,
                              stdin=subprocess.PIPE,
                              stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE)
        output, err = sp.communicate(input_text)
        self.assertEqual(output, output_ref)

        output = subprocess.check_output([gs_path, "-d"]).splitlines()
        self.assertEqual(output[-1], "Will not rebuild history")

        # corrupt the cache structure
        shelve.open(cache_path)["history"] = {
            "linux.git" : ["abc", "abc", "abc"],
            "net" : ["abc", "abc", "abc"],
            "net-next" : ["abc", "abc", "abc"],
        }
        output = subprocess.check_output([gs_path, "-d"]).splitlines()
        self.assertEqual(output[1], "Inconsistent cache content")
        self.assertEqual(output[-1], "Will rebuild history")

        sp = subprocess.Popen(gs_path,
                              stdin=subprocess.PIPE,
                              stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE)
        output, err = sp.communicate(input_text)
        self.assertEqual(output, output_ref)

        output = subprocess.check_output([gs_path, "-d"]).splitlines()
        self.assertEqual(output[-1], "Will not rebuild history")


if __name__ == '__main__':
    # Run a single testcase
    suite = unittest.TestLoader().loadTestsFromTestCase(TestIndexLinux)
    unittest.TextTestRunner(verbosity=2).run(suite)
