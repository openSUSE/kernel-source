#!/usr/bin/python
# -*- coding: utf-8 -*-

from __future__ import print_function

import collections
import itertools
import os
import pygit2
import shutil
import subprocess
import sys
import tempfile
import unittest

import git_sort


class TestRepoURL(unittest.TestCase):
    def test_eq(self):
        self.assertEqual(
            git_sort.RepoURL("git://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git"),
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

        #sys.stdin.readline()


    def tearDown(self):
        shutil.rmtree(os.environ["XDG_CACHE_HOME"])
        shutil.rmtree(self.repo_dir)


    def test_index(self):
        self.assertEqual(
            self.index.repo_heads,
            collections.OrderedDict([
                (git_sort.Head(git_sort.RepoURL(None), "HEAD"),
                 str(self.commits[-1][0]),)])
        )


    def test_sort(self):
        mapping = {commit : subject for commit, subject in self.commits}
        r = self.index.sort(mapping)
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

        self.repo.checkout("ref/heads/mainline")

        m1 = self.repo.create_commit(
            "refs/heads/net",
            author,
            committer,
            "mainline 1, merge net\n\nlog",
            tree,
            [m0, n0]
        )

        self.index = git_sort.SortIndex(self.repo)

        sys.stdin.readline()


    def tearDown(self):
        shutil.rmtree(os.environ["XDG_CACHE_HOME"])
        shutil.rmtree(self.repo_dir)


    def test_index(self):
        self.assertTrue(True)
