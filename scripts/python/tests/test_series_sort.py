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

        oot0 = self.repo.create_commit(
            "refs/heads/oot",
            author,
            committer,
            "oot 0\n\nlog",
            tree,
            [m0]
        )

        oot1 = self.repo.create_commit(
            "refs/heads/oot",
            author,
            committer,
            "oot 1\n\nlog",
            tree,
            [oot0]
        )

        k_org_canon_prefix = "git://git.kernel.org/pub/scm/linux/kernel/git/"
        origin_repo = k_org_canon_prefix + "torvalds/linux.git"
        self.repo.remotes.create("origin", origin_repo)
        self.repo.references.create("refs/remotes/origin/master", m2)

        net_repo = k_org_canon_prefix + "davem/net.git"
        self.repo.remotes.create("net", net_repo)
        self.repo.references.create("refs/remotes/net/master", n2)

        self.index = git_sort.SortIndex(self.repo)

        # setup stub kernel-source content
        self.ks_dir = tempfile.mkdtemp(prefix="gs_ks")
        patch_dir = Path(self.ks_dir, "patches.suse")
        patch_dir.mkdir()
        tests.support.format_patch(self.repo.get(m0), directory=patch_dir, mainline="v3.45-rc6")
        tests.support.format_patch(self.repo.get(n0), directory=patch_dir, mainline="v3.45-rc6")
        tests.support.format_patch(self.repo.get(n1), directory=patch_dir, repo=net_repo)
        tests.support.format_patch(self.repo.get(n2), directory=patch_dir, repo=net_repo)
        tests.support.format_patch(self.repo.get(oot0), directory=patch_dir)
        tests.support.format_patch(self.repo.get(oot1), directory=patch_dir, mainline="Submitted http://lore.kernel.org/somelist/somemessage")


    def tearDown(self):
        shutil.rmtree(os.environ["XDG_CACHE_HOME"])
        shutil.rmtree(os.environ["LINUX_GIT"])
        shutil.rmtree(self.ks_dir)


    def test_nofile(self):
        try:
            subprocess.check_output([lib.ss_path, 'aaa'],
                                    cwd=self.ks_dir, stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError as err:
            self.assertEqual(err.returncode, 1)
            self.assertEqual(
                err.output.decode(),
                "Error: [Errno 2] No such file or directory: 'aaa'\n")
        else:
            self.assertTrue(False)


    def test_absent(self):
        (tmp, series,) = tempfile.mkstemp(dir=self.ks_dir)
        with open(series, mode="w") as f:
            f.write(
"""
	patches.suse/unsorted-before.patch
""")

        try:
            subprocess.check_output([lib.ss_path, series],
                                    cwd=self.ks_dir, stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError as err:
            self.assertEqual(err.output.decode(), "Error: Sorted subseries not found.\n")
        else:
            self.assertTrue(False)

        os.unlink(series)


    def test_sort_small(self):
        (tmp, series,) = tempfile.mkstemp(dir=self.ks_dir)
        with open(series, mode="w") as f:
            f.write(tests.support.format_series((
                (None, (
                    "patches.suse/mainline-0.patch",
                    "patches.suse/net-0.patch",
                )),
            )))

        subprocess.check_call([lib.ss_path, '-c', series], cwd=self.ks_dir)
        with open(series) as f:
            content1 = f.read()
        subprocess.check_call([lib.ss_path, series], cwd=self.ks_dir)
        with open(series) as f:
            content2 = f.read()
        self.assertEqual(content2, content1)

        os.unlink(series)


    def test_sort(self):
        (tmp, series,) = tempfile.mkstemp(dir=self.ks_dir)
        with open(series, mode="w") as f:
            f.write(
"""
	patches.suse/unsorted-before.patch

	########################################################
	# sorted patches
	########################################################
	patches.suse/mainline-0.patch
	patches.suse/net-0.patch

	# davem/net
	patches.suse/net-1.patch
	patches.suse/net-2.patch

	# out-of-tree patches
	patches.suse/oot-0.patch
	patches.suse/oot-1.patch

	########################################################
	# end of sorted patches
	########################################################

	patches.suse/unsorted-after.patch
""")

        subprocess.check_call([lib.ss_path, '-c', series], cwd=self.ks_dir)
        with open(series) as f:
            content1 = f.read()
        subprocess.check_call([lib.ss_path, series], cwd=self.ks_dir)
        with open(series) as f:
            content2 = f.read()
        self.assertEqual(content2, content1)

        os.unlink(series)


    def test_sort_empty(self):
        (tmp, series,) = tempfile.mkstemp(dir=self.ks_dir)
        with open(series, mode="w") as f:
            f.write(
"""
	patches.suse/unsorted-before.patch

	########################################################
	# sorted patches
	########################################################

	########################################################
	# end of sorted patches
	########################################################

	patches.suse/unsorted-after.patch
""")

        subprocess.check_call([lib.ss_path, '-c', series], cwd=self.ks_dir)
        with open(series) as f:
            content1 = f.read()
        subprocess.check_call([lib.ss_path, series], cwd=self.ks_dir)
        with open(series) as f:
            content2 = f.read()
        self.assertEqual(content2, content1)

        os.unlink(series)


class TestFromPatch(unittest.TestCase):
    """
    The naming of these tests stems from the following factors which determine
    how a patch is sorted:
        * commit found in index
        * patch's series.conf current_head is indexed (ie. the local repo
          fetches from that remote)
        * patch appears to have moved downstream/didn't move/upstream
        * patch's tag is good ("Git-repo:" == current_head.url)
        * patches may be moved upstream between subsystem sections
    """

    def setUp(self):
        self.maxDiff = None

        os.environ["XDG_CACHE_HOME"] = tempfile.mkdtemp(prefix="gs_cache")

        # setup stub linux repository
        os.environ["LINUX_GIT"] = tempfile.mkdtemp(prefix="gs_repo")
        self.repo = pygit2.init_repository(os.environ["LINUX_GIT"])

        author = pygit2.Signature("Alice Author", "alice@authors.tld", time=0,
                                  offset=0)
        committer = pygit2.Signature("Cecil Committer", "cecil@committers.tld",
                                    time=0, offset=0)
        tree = self.repo.TreeBuilder()

        k_org_canon_prefix = "git://git.kernel.org/pub/scm/linux/kernel/git/"
        self.mainline_repo = k_org_canon_prefix + "torvalds/linux.git"
        self.repo.remotes.create("origin", self.mainline_repo)
        self.net_next_repo = k_org_canon_prefix + "davem/net-next.git"
        self.repo.remotes.create("net-next", self.net_next_repo)
        self.net_repo = k_org_canon_prefix + "davem/net.git"
        self.rdma_repo = k_org_canon_prefix + "rdma/rdma.git"
        self.repo.remotes.create("rdma", self.rdma_repo)
        self.dledford_repo = k_org_canon_prefix + "dledford/rdma.git"
        self.repo.remotes.create("dledford/rdma", self.dledford_repo)
        self.nf_repo = k_org_canon_prefix + "netfilter/nf.git"
        self.repo.remotes.create("netfilter/nf", self.nf_repo)

        self.commits = {}
        self.commits["mainline 0"] = self.repo.create_commit(
            "refs/heads/mainline",
            author,
            committer,
            "mainline 0\n\nlog",
            tree.write(),
            []
        )

        self.commits["net-next 0"] = self.repo.create_commit(
            "refs/heads/net-next",
            author,
            committer,
            "net-next 0\n\nlog",
            tree.write(),
            [self.commits["mainline 0"]]
        )
        self.repo.references.create("refs/remotes/net-next/master",
                                    self.commits["net-next 0"])

        self.commits["other 0"] = self.repo.create_commit(
            "refs/heads/other",
            author,
            committer,
            "other 0\n\nlog",
            tree.write(),
            [self.commits["mainline 0"]]
        )

        self.commits["rdma for-next 0"] = self.repo.create_commit(
            "refs/heads/rdma-next",
            author,
            committer,
            "rdma for-next 0\n\nlog",
            tree.write(),
            [self.commits["mainline 0"]]
        )

        self.commits["mainline 1"] = self.repo.create_commit(
            "refs/heads/mainline",
            author,
            committer,
            "mainline 1, merge rdma\n\nlog",
            tree.write(),
            [self.commits["mainline 0"], self.commits["rdma for-next 0"]]
        )

        self.commits["dledford/rdma k.o/for-next 0"] = self.repo.create_commit(
            "refs/heads/dledford-next",
            author,
            committer,
            "dledford/rdma k.o/for-next 0\n\nlog",
            tree.write(),
            [self.commits["rdma for-next 0"]]
        )
        self.repo.references.create(
            "refs/remotes/dledford/rdma/k.o/for-next",
            self.commits["dledford/rdma k.o/for-next 0"])
        self.repo.references.create("refs/remotes/rdma/for-next",
                                    self.commits["dledford/rdma k.o/for-next 0"])
        self.repo.references.create("refs/remotes/rdma/for-rc",
                                    self.commits["dledford/rdma k.o/for-next 0"])

        self.commits["net 0"] = self.repo.create_commit(
            "refs/heads/net",
            author,
            committer,
            "net 0\n\nlog",
            tree.write(),
            [self.commits["mainline 0"]]
        )

        self.commits["nf 0"] = self.repo.create_commit(
            "refs/heads/nf",
            author,
            committer,
            "nf 0\n\nlog",
            tree.write(),
            [self.commits["mainline 0"]]
        )
        self.repo.references.create("refs/remotes/netfilter/nf/master",
                                    self.commits["nf 0"])

        self.commits["mainline 2"] = self.repo.create_commit(
            "refs/heads/mainline",
            author,
            committer,
            "mainline 2, merge net\n\nlog",
            tree.write(),
            [self.commits["mainline 1"], self.commits["net 0"]]
        )

        self.commits["net 1"] = self.repo.create_commit(
            "refs/heads/net",
            author,
            committer,
            "net 1\n\nlog",
            tree.write(),
            [self.commits["net 0"]]
        )

        tree.insert("README", 
                    self.repo.create_blob("NAME = v4.1 release\n"),
                    pygit2.GIT_FILEMODE_BLOB)
        self.commits["v4.1"] = self.repo.create_commit(
            "refs/heads/mainline",
            author,
            committer,
            "Linux 4.1",
            tree.write(),
            [self.commits["mainline 2"]]
        )
        self.repo.references.create("refs/remotes/origin/master",
                                    self.commits["v4.1"])
        self.repo.create_tag("v4.1", self.commits["v4.1"], pygit2.GIT_REF_OID,
                             committer, "Linux 4.1")

        self.repo.checkout("refs/heads/mainline")

        # setup stub kernel-source content
        self.ks_dir = Path(tempfile.mkdtemp(prefix="gs_ks"))
        self.patch_dir = self.ks_dir / "patches.suse"
        self.patch_dir.mkdir()


    def tearDown(self):
        shutil.rmtree(os.environ["XDG_CACHE_HOME"])
        shutil.rmtree(os.environ["LINUX_GIT"])
        shutil.rmtree(self.ks_dir)


    def check_tag(self, patch, tag, value):
        with patch.open() as f:
            for line in f:
                if line.startswith(tag):
                    self.assertEqual(line[len(tag):-1], value)


    def _transform_arg(move_upstream):
        if move_upstream is None:
            return [[], ["-u"]]
        elif move_upstream:
            return [["-u"]]
        else:
            return [[]]


    def check_failure(self, msg, move_upstream=None):
        for extra_arg in self.__class__._transform_arg(move_upstream):
            try:
                subprocess.check_output(
                    [lib.ss_path] + extra_arg + ['-c', 'series.conf'],
                    cwd=self.ks_dir, stderr=subprocess.STDOUT)
            except subprocess.CalledProcessError as err:
                self.assertEqual(err.returncode, 1)
                self.assertTrue(err.output.decode(), msg)
            else:
                self.assertTrue(False)

            try:
                subprocess.check_output(
                    [lib.ss_path] + extra_arg + ['series.conf'],
                    cwd=self.ks_dir, stderr=subprocess.STDOUT)
            except subprocess.CalledProcessError as err:
                self.assertEqual(err.returncode, 1)
                self.assertEqual(err.output.decode(), msg)
            else:
                self.assertTrue(False)


    def check_constant(self, name, move_upstream=None):
        for extra_arg in self.__class__._transform_arg(move_upstream):
            subprocess.check_call(
                [lib.ss_path] + extra_arg + ['-c', 'series.conf'], cwd=self.ks_dir)

            series1 = (self.ks_dir / 'series.conf').read_text()
            patch1 = (self.ks_dir / name).read_text()
            subprocess.check_call([lib.ss_path] + extra_arg + ['series.conf'], cwd=self.ks_dir)
            series2 = (self.ks_dir / 'series.conf').read_text()
            patch2 = (self.ks_dir / name).read_text()
            self.assertEqual(series2, series1)
            self.assertEqual(patch2, patch1)


    def check_outdated(self, name, msg, series2, move_upstream=None):
        (tmp, series,) = tempfile.mkstemp(dir=self.ks_dir)
        (tmp, patch,) = tempfile.mkstemp(dir=self.ks_dir)
        shutil.copy(name, patch)

        for extra_arg in self.__class__._transform_arg(move_upstream):
            shutil.copy(patch, name)
            try:
                subprocess.check_output(
                    [lib.ss_path] + extra_arg + ['-c', 'series.conf'],
                    cwd=self.ks_dir, stderr=subprocess.STDOUT)
            except subprocess.CalledProcessError as err:
                self.assertEqual(err.returncode, 2)
                self.assertEqual(err.output.decode(), msg)
            else:
                self.assertTrue(False)

            shutil.copy(self.ks_dir / 'series.conf', series)
            subprocess.check_call([lib.ss_path] + extra_arg + [series], cwd=self.ks_dir)
            with open(series) as f:
                content2 = f.read()
            self.assertEqual(content2, series2)

        os.unlink(series)
        os.unlink(patch)


    def test_found_indexed_downstream_good(self):
        """
        patch sorted in mainline, commit found in net-next
            error, possible causes:
                mainline repo is outdated
                    because it was not found in mainline index/appears to have
                    moved downstream
                order in remotes is wrong
                    because it appears to have moved downstream
                section and Git-repo are wrong
                    because it appears to have moved downstream and tag is good
        """

        name = tests.support.format_patch(
            self.repo.get(self.commits["net-next 0"]), mainline="v0",
            directory=self.patch_dir)

        (self.ks_dir / 'series.conf').write_text(
            tests.support.format_series((
                (None, (
                    name,
                )),
            )))

        self.check_failure(
"Error: There is a problem with patch \"%s\". The patch is in the wrong section of series.conf or the remote fetching from \"torvalds/linux\" needs to be fetched or the relative order of \"davem/net-next\" and \"torvalds/linux\" in \"remotes\" is incorrect. Manual intervention is required.\n" % (name,))


    def test_found_indexed_downstream_bad(self):
        """
        patch sorted in mainline, commit found in net-next
            error, possible causes:
                mainline repo is outdated
                    because it was not found in mainline index/appears to have
                    moved downstream
                section is wrong or Git-repo is wrong
                    because it appears to have moved downstream and the two
                    differ
        """
        name = tests.support.format_patch(
            self.repo.get(self.commits["net-next 0"]), repo=self.net_next_repo,
            directory=self.patch_dir)

        (self.ks_dir / 'series.conf').write_text(
            tests.support.format_series((
                (None, (
                    name,
                )),
            )))

        self.check_failure(
"Error: There is a problem with patch \"%s\". The patch is in the wrong section of series.conf or the remote fetching from \"torvalds/linux\" needs to be fetched. Manual intervention is required.\n" % (name,))


    def test_found_indexed_nomove_good(self):
        """
        patch sorted in net-next
            stays there
        """
        name = tests.support.format_patch(
            self.repo.get(self.commits["net-next 0"]), repo=self.net_next_repo,
            directory=self.patch_dir)

        (self.ks_dir / 'series.conf').write_text(
            tests.support.format_series((
                ("davem/net-next", (
                    name,
                )),
            )))

        self.check_constant(name)


    def test_found_indexed_nomove_bad(self):
        """
        patch sorted in net-next, tagged with mainline
            stays there
            update tag
        """
        name = tests.support.format_patch(
            self.repo.get(self.commits["net-next 0"]), repo=self.net_repo,
            directory=self.patch_dir)

        series1 = tests.support.format_series((
            ("davem/net-next", (
                name,
            )),
        ))
        (self.ks_dir / 'series.conf').write_text(series1)

        self.check_outdated(name, "Git-repo tags are outdated.\n", series1)
        self.check_tag(name, "Git-repo: ", self.net_next_repo)


    def prepare_found_indexed_upstream_good(self):
        name = tests.support.format_patch(
            self.repo.get(self.commits["rdma for-next 0"]), repo=self.rdma_repo,
            directory=self.patch_dir)

        (self.ks_dir / 'series.conf').write_text(
            tests.support.format_series((
                ("rdma/rdma for-next", (
                    name,
                )),
            )))

        series2 = tests.support.format_series((
            (None, (
                name,
            )),
        ))

        return name, series2


    def test_found_indexed_upstream_good_moveupstream(self):
        """
        patch sorted in rdma for-next, commit found in mainline
            moves to mainline
            tag is updated
        """
        name, series2 = self.prepare_found_indexed_upstream_good()

        self.check_outdated(name,
            "Input is not sorted.\nGit-repo tags are outdated.\n", series2,
            True)
        self.check_tag(name, "Git-repo: ", self.mainline_repo)


    def test_found_indexed_upstream_good_nomoveupstream(self):
        """
        patch sorted in rdma for-next, commit found in mainline
            stays there
        """
        name, series2 = self.prepare_found_indexed_upstream_good()

        self.check_constant(name, False)


    def prepare_found_indexed_upstream_bad2(self):
        alt_repo = self.rdma_repo.replace("git://", "https://")

        name = tests.support.format_patch(
            self.repo.get(self.commits["dledford/rdma k.o/for-next 0"]),
            repo=alt_repo, directory=self.patch_dir)

        (self.ks_dir / 'series.conf').write_text(
            tests.support.format_series((
                ("dledford/rdma k.o/for-next", (
                    name,
                )),
            )))

        series2 = tests.support.format_series((
            ("rdma/rdma for-rc", (
                name,
            )),
        ))

        return name, series2, alt_repo


    def test_found_indexed_upstream_bad2_moveupstream(self):
        """
        patch sorted in dledford/rdma k.o/for-next, tagged with rdma/rdma,
        commit found in rdma/rdma for-rc
            moves to rdma/rdma for-rc
            tag is NOT updated

        This is a special case. See the log of commit 0ac6457e94e8
        ("scripts/git_sort/lib.py: Rewrite Git-repo only if it differs.")
        """
        name, series2, alt_repo = self.prepare_found_indexed_upstream_bad2()

        self.check_outdated(name, "Input is not sorted.\n", series2, True)
        self.check_tag(name, "Git-repo: ", alt_repo)


    def test_found_indexed_upstream_bad2_nomoveupstream(self):
        """
        patch sorted in dledford/rdma k.o/for-next, tagged with rdma/rdma,
        commit found in rdma/rdma for-rc
            error, possible causes:
                section is wrong or Git-repo is wrong
                    because they differ and there is no way to know which head
                    the user intended.
        """
        name, series2, alt_repo = self.prepare_found_indexed_upstream_bad2()

        self.check_failure(
"Error: There is a problem with patch \"%s\". The Git-repo tag is incorrect or the patch is in the wrong section of series.conf. Manual intervention is required.\n" % (name,), False)


    def test_found_notindexed_downstream_good(self):
        """
        patch sorted in net (not fetched), commit found in net-next
            stays there
        """
        name = tests.support.format_patch(
            self.repo.get(self.commits["net-next 0"]), repo=self.net_repo,
            directory=self.patch_dir)

        (self.ks_dir / 'series.conf').write_text(
            tests.support.format_series((
                ("davem/net", (
                    name,
                )),
            )))

        self.check_constant(name)


    def test_found_notindexed_downstream_bad(self):
        """
        patch sorted in net (not fetched), commit found in net-next,
        git-repo tag is bad
            error, possible causes:
                section is wrong or Git-repo is wrong
                    because they differ and there is no (usual) scenario where
                    commits move downstream
        """
        name = tests.support.format_patch(
            self.repo.get(self.commits["net-next 0"]), repo=self.rdma_repo,
            directory=self.patch_dir)

        (self.ks_dir / 'series.conf').write_text(
            tests.support.format_series((
                ("davem/net", (
                    name,
                )),
            )))

        self.check_failure(
"Error: There is a problem with patch \"%s\". The Git-repo tag is incorrect or the patch is in the wrong section of series.conf. Manual intervention is required.\n" % (name,))


    # test_found_notindexed_nomove_NA()
    # cannot be tested (without stubbing some code to return invalid data)


    def prepare_found_notindexed_upstream_good(self):
        name = tests.support.format_patch(
            self.repo.get(self.commits["net 0"]), repo=self.net_repo,
            directory=self.patch_dir)

        (self.ks_dir / 'series.conf').write_text(
            tests.support.format_series((
                ("davem/net", (
                    name,
                )),
            )))

        series2 = tests.support.format_series((
            (None, (
                name,
            )),
        ))

        return name, series2


    @staticmethod
    def filter_out_tags(name):
        with name.open() as f:
            result = [line
                      for line in f
                      if not line.startswith(("Git-repo", "Patch-mainline",))]

        return result


    def test_found_notindexed_upstream_good_moveupstream(self):
        """
        patch sorted in net (not fetched), commit found in mainline
            moves to mainline
            tag is updated
        """
        name, series2 = self.prepare_found_notindexed_upstream_good()
        before = self.filter_out_tags(name)

        self.check_outdated(name,
            "Input is not sorted.\nGit-repo tags are outdated.\n", series2,
            True)
        self.check_tag(name, "Git-repo: ", self.mainline_repo)

        # check that only the expected tags changed
        after = self.filter_out_tags(name)
        self.assertEqual(before, after)


    def test_found_notindexed_upstream_good_nomoveupstream(self):
        """
        patch sorted in net (not fetched), commit found in mainline
            stays there
        """
        name, series2 = self.prepare_found_notindexed_upstream_good()

        self.check_constant(name, False)

    def prepare_found_notindexed_upstream_bad2(self):
        alt_repo = self.nf_repo.replace("git://", "https://")

        name = tests.support.format_patch(
            self.repo.get(self.commits["nf 0"]), repo=alt_repo,
            directory=self.patch_dir)

        (self.ks_dir / 'series.conf').write_text(
            tests.support.format_series((
                ("netfilter/nf-next", (
                    name,
                )),
            )))

        series2 = tests.support.format_series((
            ("netfilter/nf", (
                name,
            )),
        ))

        return name, series2, alt_repo


    def test_found_notindexed_upstream_bad2_moveupstream(self):
        """
        patch sorted in netfilter nf-next (not fetched), commit found in netfilter nf,
        git-repo tag is bad
            moves to netfilter nf
            tag is NOT updated

        This is a special case. See the log of commit 0ac6457e94e8
        ("scripts/git_sort/lib.py: Rewrite Git-repo only if it differs.")
        """
        name, series2, alt_repo = self.prepare_found_notindexed_upstream_bad2()

        self.check_outdated(name, "Input is not sorted.\n", series2, True)
        self.check_tag(name, "Git-repo: ", alt_repo)


    def test_found_notindexed_upstream_bad2_nomoveupstream(self):
        """
        patch sorted in netfilter nf-next (not fetched), commit found in netfilter nf,
        git-repo tag is bad
            error, possible causes:
                section is wrong or Git-repo is wrong
                    because they differ and there is no way to know which head
                    the user intended.
        """
        name, series2, alt_repo = self.prepare_found_notindexed_upstream_bad2()

        self.check_failure(
"Error: There is a problem with patch \"%s\". The Git-repo tag is incorrect or the patch is in the wrong section of series.conf. Manual intervention is required.\n" % (name,), False)


    def test_notfound_indexed_NA_good(self):
        """
        patch sorted in net-next
            error, possible causes:
                net-next repo is outdated
                Git-commit is wrong
                section and Git-repo are wrong
        """
        commit = self.repo.get(self.commits["other 0"])
        name = tests.support.format_patch(commit, repo=self.net_next_repo,
                                          directory=self.patch_dir)

        (self.ks_dir / 'series.conf').write_text(
            tests.support.format_series((
                ("davem/net-next", (
                    name,
                )),
            )))

        self.check_failure(
"Error: There is a problem with patch \"%s\". Commit \"%s\" not found in git-sort index. The remote fetching from \"davem/net-next\" needs to be fetched or the Git-commit tag is incorrect or the patch is in the wrong section of series.conf. Manual intervention is required.\n" % (name, str(commit.id),))


    def test_notfound_indexed_NA_bad(self):
        """
        patch sorted in net-next, git-repo tag is bad
            error, possible causes:
                section or Git-repo are wrong
        """
        name = tests.support.format_patch(
            self.repo.get(self.commits["other 0"]), repo=self.rdma_repo,
            directory=self.patch_dir)

        (self.ks_dir / 'series.conf').write_text(
            tests.support.format_series((
                ("davem/net-next", (
                    name,
                )),
            )))

        self.check_failure(
"Error: There is a problem with patch \"%s\". The Git-repo tag is incorrect or the patch is in the wrong section of series.conf. Manual intervention is required.\n" % (name,))


    def test_notfound_notindexed_NA_good(self):
        """
        patch sorted in net
            stays there
        """
        name = tests.support.format_patch(
            self.repo.get(self.commits["net 1"]), repo=self.net_repo,
            directory=self.patch_dir)

        (self.ks_dir / 'series.conf').write_text(
            tests.support.format_series((
                ("davem/net", (
                    name,
                )),
            )))

        self.check_constant(name)


    def test_notfound_notindexed_NA_bad(self):
        """
        patch sorted in net, bad git-repo tag
            error, possible causes:
                Git-repo is wrong
                series.conf section is wrong and (git-commit is wrong or the
                remote is outdated or not available locally
                Git-repo is not indexed because it's missing in git_sort.py's
                remote list
        """
        name = tests.support.format_patch(
            self.repo.get(self.commits["net 1"]), repo=self.rdma_repo,
            directory=self.patch_dir)

        (self.ks_dir / 'series.conf').write_text(
            tests.support.format_series((
                ("davem/net", (
                    name,
                )),
            )))

        self.check_failure(
"Error: There is a problem with patch \"%s\". The Git-repo tag is incorrect or the patch is in the wrong section of series.conf and (the Git-commit tag is incorrect or the relevant remote is outdated or not available locally) or an entry for this repository is missing from \"remotes\". In the last case, please edit \"remotes\" in \"scripts/git_sort/git_sort.yaml\" and commit the result. Manual intervention is required.\n" % (name,))


    def test_malformed(self):
        """
        Generate a series and destroy the Git-commit tag on one of the patches
        This should report a specific error so that this situation is not conflated with wrong Patch-mainline tag in out-of-tree section
        """

        name, series2 = self.prepare_found_indexed_upstream_good()
        subprocess.call(['sed', '-i', '-e', 's/commit/comit/', name], cwd='/')
        self.check_failure(
'Error: There is a problem with patch "%s". The Patch-mainline tag "Queued in subsystem maintainer repository" requires Git-commit.\n' % (name))


if __name__ == '__main__':
    # Run a single testcase
    suite = unittest.TestLoader().loadTestsFromTestCase(TestFromPatch)
    unittest.TextTestRunner(verbosity=2).run(suite)
