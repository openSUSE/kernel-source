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


@unittest.skip("Patched quilt not maintained")
class TestQuiltMode(unittest.TestCase):
    def setUp(self):
        os.environ["XDG_CACHE_HOME"] = tempfile.mkdtemp(prefix="gs_cache")

        # setup stub linux repository
        os.environ["LINUX_GIT"] = tempfile.mkdtemp(prefix="gs_repo")
        self.repo = pygit2.init_repository(os.environ["LINUX_GIT"])
        self.repo.config["user.email"] = "agraf@suse.de"
        self.repo.config["user.name"] = "Alexander Graf"

        author = pygit2.Signature("Alice Author", "alice@authors.tld")
        committer = pygit2.Signature("Cecil Committer", "cecil@committers.tld")
        tree = self.repo.TreeBuilder()

        tree.insert("README", 
                    self.repo.create_blob("NAME = Roaring Lionus\n"),
                    pygit2.GIT_FILEMODE_BLOB)
        self.commits = []
        self.commits.append(self.repo.create_commit(
            "refs/heads/mainline",
            author,
            committer,
            "Linux 4.9",
            tree.write(),
            []
        ))
        self.repo.create_tag("v4.9", self.commits[-1], pygit2.GIT_REF_OID,
                             committer, "Linux 4.9")

        tree.insert("README", 
                    self.repo.create_blob("NAME = Anniversary Edition\n"),
                    pygit2.GIT_FILEMODE_BLOB)
        self.commits.append(self.repo.create_commit(
            "refs/heads/mainline",
            author,
            committer,
            "Linux 4.10-rc5",
            tree.write(),
            [self.commits[-1]]
        ))
        self.repo.create_tag("v4.10-rc5", self.commits[-1], pygit2.GIT_REF_OID,
                             committer, "Linux 4.10-rc5")

        tree.insert("driver.c", 
                    self.repo.create_blob("#include <linux/module.h>\n"),
                    pygit2.GIT_FILEMODE_BLOB)
        author2 = pygit2.Signature("Marc Zyngier", "marc.zyngier@arm.com")
        self.commits.append(self.repo.create_commit(
            "refs/heads/mainline",
            author2,
            author2,
            """KVM: arm/arm64: vgic-v3: Add accessors for the ICH_APxRn_EL2 registers

As we're about to access the Active Priority registers a lot more,
let's define accessors that take the register number as a parameter.

Tested-by: Alexander Graf <agraf@suse.de>
Acked-by: David Daney <david.daney@cavium.com>
Reviewed-by: Eric Auger <eric.auger@redhat.com>
Signed-off-by: Marc Zyngier <marc.zyngier@arm.com>
Signed-off-by: Christoffer Dall <cdall@linaro.org>
""",
            tree.write(),
            [self.commits[-1]]
        ))

        tree.insert("core.c", 
                    self.repo.create_blob("#include <linux/kernel.h>\n"),
                    pygit2.GIT_FILEMODE_BLOB)
        author3 = pygit2.Signature("Peter Zijlstra", "peterz@infradead.org")
        self.commits.append(self.repo.create_commit(
            "refs/heads/mainline",
            author3,
            author3,
            """sched/debug: Ignore TASK_IDLE for SysRq-W

Markus reported that tasks in TASK_IDLE state are reported by SysRq-W,
which results in undesirable clutter.

Reported-by: Markus Trippelsdorf <markus@trippelsdorf.de>
Signed-off-by: Peter Zijlstra (Intel) <peterz@infradead.org>
Cc: Linus Torvalds <torvalds@linux-foundation.org>
Cc: Peter Zijlstra <peterz@infradead.org>
Cc: Thomas Gleixner <tglx@linutronix.de>
Cc: linux-kernel@vger.kernel.org
Signed-off-by: Ingo Molnar <mingo@kernel.org>
""",
            tree.write(),
            [self.commits[-1]]
        ))

        tree.insert("README", 
                    self.repo.create_blob("NAME = Fearless Coyote\n"),
                    pygit2.GIT_FILEMODE_BLOB)
        self.commits.append(self.repo.create_commit(
            "refs/heads/mainline",
            author,
            committer,
            "Linux 4.10-rc6",
            tree.write(),
            [self.commits[-1]]
        ))
        self.repo.create_tag("v4.10-rc6", self.commits[-1], pygit2.GIT_REF_OID,
                             committer, "Linux 4.10-rc6")

        self.repo.remotes.create(
            "origin",
            "git://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git")
        self.repo.references.create("refs/remotes/origin/master",
                                    self.commits[-1])

        # setup stub kernel-source content
        self.ks_dir = Path(tempfile.mkdtemp(prefix="gs_ks"))
        patch_dir = self.ks_dir / "patches.suse"
        patch_dir.mkdir()
        with (self.ks_dir / 'series.conf').open('w') as f:
            f.write(
"""# Kernel patches configuration file

	########################################################
	# sorted patches
	########################################################
""")
            for commit, tag in (
                (self.commits[0], "v4.9",),
                (self.commits[1], "v4.10-rc5",),
            ):
                f.write("\tpatches.suse/%s\n" % (
                    tests.support.format_patch(self.repo.get(commit),
                                               directory=patch_dir,
                                               mainline=tag).relative_to(patch_dir),))
            f.write(
"""
	########################################################
	# end of sorted patches
	########################################################
""")


        # This overlaps what is tested by test_series_sort, hence, not put in a
        # test of its own.
        subprocess.check_call([lib.ss_path, '-c', 'series.conf'], cwd=self.ks_dir)
        content1 = (self.ks_dir / 'series.conf').read_text()
        subprocess.check_call([lib.ss_path, 'series.conf'], cwd=self.ks_dir)
        content2 = (self.ks_dir / 'series.conf').read_text()
        self.assertEqual(content2, content1)

        pygit2.init_repository(self.ks_dir)
        subprocess.check_call(("git", "add", "series.conf", "patches.suse",),
                              cwd=self.ks_dir, stdout=subprocess.DEVNULL)
        subprocess.check_call(("git", "commit", "-m", "import",),
                              cwd=self.ks_dir, stdout=subprocess.DEVNULL)

        self.current = self.ks_dir / 'tmp/current'
        self.current.mkdir(parents=True)
        subprocess.check_call(
            ["quilt", "setup", "--sourcedir", "../../", "../../series.conf"], cwd=self.current)


    def tearDown(self):
        shutil.rmtree(os.environ["XDG_CACHE_HOME"])
        shutil.rmtree(os.environ["LINUX_GIT"])
        shutil.rmtree(self.ks_dir)


    def test_quilt_mode(self):
        series = self.current / 'series'

        # test series file replacement
        with series.open() as f:
            entries = ["%s\n" % (l,) for l in
                       [line.strip() for line in f.readlines()]
                       if l and not l.startswith("#")]
        # remove the symlink
        series.unlink()
        with series.open('w') as f:
            f.writelines(entries)
        subprocess.check_call(
            [lib.bindir / 'qgoto.py', str(self.commits[0])],
            cwd=self.current, stdout=subprocess.DEVNULL)

        # test qgoto
        subprocess.check_call(
            ". %s; qgoto %s" % (lib.qm_path, str(self.commits[0])), shell=True,
            cwd=self.current, stdout=subprocess.DEVNULL, executable="/bin/bash")

        # test qdupcheck
        try:
            subprocess.check_output(
                ". %s; qdupcheck %s" % (lib.qm_path, str(self.commits[1])),
                cwd=self.current, shell=True, executable="/bin/bash")
        except subprocess.CalledProcessError as err:
            self.assertEqual(err.returncode, 1)
            self.assertEqual(err.output.decode().splitlines()[-1].strip(),
                             "patches.suse/Linux-4.10-rc5.patch")
        else:
            self.assertTrue(False)

        subprocess.check_call(
            ". %s; qgoto %s" % (lib.qm_path, str(self.commits[1])), shell=True,
            cwd=self.current, stdout=subprocess.DEVNULL, executable="/bin/bash")

        try:
            subprocess.check_output(
                ". %s; qdupcheck %s" % (lib.qm_path, str(self.commits[1])),
                cwd=self.current, shell=True, executable="/bin/bash")
        except subprocess.CalledProcessError as err:
            self.assertEqual(err.returncode, 1)
            self.assertEqual(err.output.decode().splitlines()[-1].strip(),
                             "This is the top patch.")
        else:
            self.assertTrue(False)

        # import commits[2]
        subprocess.check_call(
            ". %s; qgoto %s" % (lib.qm_path, str(self.commits[2])), shell=True,
            cwd=self.current, executable="/bin/bash")
        subprocess.check_call(
            """. %s; qcp -r "bsc#1077761" -d patches.suse %s""" % (
                lib.qm_path, str(self.commits[2])),
            cwd=self.current, shell=True, stdout=subprocess.DEVNULL, executable="/bin/bash")

        retval = subprocess.check_output(("quilt", "--quiltrc", "-", "next",), cwd=self.current)
        name = "patches.suse/KVM-arm-arm64-vgic-v3-Add-accessors-for-the-ICH_APxR.patch"
        self.assertEqual(retval.decode().strip(), name)

        try:
            with (self.ks_dir / name).open() as f:
                retval = f.readlines().index(
                    "Acked-by: Alexander Graf <agraf@suse.de>\n")
        except ValueError:
            retval = -1
        self.assertNotEqual(retval, -1)

        subprocess.check_call(("quilt", "--quiltrc", "-", "push",),
                              cwd=self.current, stdout=subprocess.DEVNULL)

        try:
            subprocess.check_output(("quilt", "--quiltrc", "-", "pop",),
                                    cwd=self.current, stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError as err:
            self.assertEqual(err.returncode, 1)
            self.assertTrue(err.output.decode().endswith(
                "needs to be refreshed first.\n"))
        else:
            self.assertTrue(False)

        subprocess.check_call(("quilt", "--quiltrc", "-", "refresh",),
                              cwd=self.current, stdout=subprocess.DEVNULL)
        subprocess.check_call(("quilt", "--quiltrc", "-", "pop",),
                              cwd=self.current, stdout=subprocess.DEVNULL)
        subprocess.check_call(("quilt", "--quiltrc", "-", "push",),
                              cwd=self.current, stdout=subprocess.DEVNULL)

        # prepare repository
        subprocess.check_call(("git", "add", "series.conf", "patches.suse",),
                       cwd=self.ks_dir, stdout=subprocess.DEVNULL)
        subprocess.check_call(
            ("git", "commit", "-m",
             "KVM: arm/arm64: vgic-v3: Add accessors for the ICH_APxRn_EL2 registers",),
            cwd=self.ks_dir, stdout=subprocess.DEVNULL)
        subprocess.check_call(("git", "checkout", "-q", "-b", "other",
                               "HEAD^",), cwd=self.ks_dir)
        shutil.rmtree(self.current)
        self.current.mkdir()
        subprocess.check_call(("quilt", "setup", "--sourcedir", "../../",
                               "../../series.conf",), cwd=self.current)

        # import commits[3]
        subprocess.check_call(
            ". %s; qgoto %s" % (lib.qm_path, str(self.commits[3])), shell=True,
            cwd=self.current, stdout=subprocess.DEVNULL, executable="/bin/bash")
        subprocess.check_call(
            """. %s; qcp -r "bsc#123" -d patches.suse %s""" % (
                lib.qm_path, str(self.commits[3])),
            cwd=self.current, shell=True, stdout=subprocess.DEVNULL, executable="/bin/bash")

        subprocess.check_call(("quilt", "--quiltrc", "-", "push",),
                              cwd=self.current, stdout=subprocess.DEVNULL)
        subprocess.check_call(("quilt", "--quiltrc", "-", "refresh",),
                              cwd=self.current, stdout=subprocess.DEVNULL)
        name = subprocess.check_output(
            ("quilt", "--quiltrc", "-", "top",), cwd=self.current).decode().strip()

        subprocess.check_call(("git", "add", "series.conf", "patches.suse",),
                              cwd=self.ks_dir, stdout=subprocess.DEVNULL)

        # test pre-commit.sh
        subprocess.check_call(lib.pc_path, cwd=self.ks_dir, stdout=subprocess.DEVNULL)

        with (self.ks_dir / 'series.conf').open() as f:
            content = f.readlines()

        content2 = list(content)
        middle = int(len(content2) / 2)
        content2[middle], content2[middle + 1] = \
            content2[middle + 1], content2[middle]

        with (self.ks_dir / 'series.conf').open('w') as f:
            f.writelines(content2)

        # check should be done against index, not working tree
        subprocess.check_call(lib.pc_path, cwd=self.ks_dir, stdout=subprocess.DEVNULL)

        subprocess.check_call(("git", "add", "series.conf",),
                              cwd=self.ks_dir, stdout=subprocess.DEVNULL)

        # ... test a bad sorted section
        try:
            subprocess.check_output(lib.pc_path, cwd=self.ks_dir, stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError as err:
            self.assertEqual(err.returncode, 1)
            self.assertTrue(err.output.decode().startswith(
                "Input is not sorted."))
        else:
            self.assertTrue(False)

        with (self.ks_dir / 'series.conf').open('w') as f:
            f.writelines(content)

        subprocess.check_call(("git", "add", "series.conf",),
                              cwd=self.ks_dir, stdout=subprocess.DEVNULL)

        subprocess.check_call(("git", "commit", "-m",
                               "sched/debug: Ignore TASK_IDLE for SysRq-W",),
                              cwd=self.ks_dir, stdout=subprocess.DEVNULL)

        # ... test a bad sorted patch
        with (self.ks_dir / name).open() as f:
            content = f.readlines()
        content2 = list(content)
        for i in range(len(content2)):
            if content2[i].startswith("Git-commit: "):
                content2[i] = "Git-commit: cb329c2e40cf6cfc7bcd7c36ce5547f95e972ea5\n"
                break
        with (self.ks_dir / name).open('w') as f:
            f.writelines(content2)
        subprocess.check_call(("git", "add", name,), cwd=self.ks_dir, stdout=subprocess.DEVNULL)

        try:
            subprocess.check_output(lib.pc_path, cwd=self.ks_dir, stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError as err:
            self.assertEqual(err.returncode, 1)
            self.assertTrue(err.output.decode().startswith(
                "Error: There is a problem with patch \"%s\"." % (name,)))
        else:
            self.assertTrue(False)

        with (self.ks_dir / name).open('w') as f:
            f.writelines(content)
        subprocess.check_call(("git", "add", name,), cwd=self.ks_dir, stdout=subprocess.DEVNULL)

        # test merge_tool.py
        subprocess.check_call(("git", "checkout", "-q", "master",), cwd=self.ks_dir)
        shutil.rmtree(self.current)
        subprocess.check_call(
            ("git", "config", "--add", "mergetool.git-sort.cmd",
             "%s $LOCAL $BASE $REMOTE $MERGED" % (
                 lib.bindir / 'merge_tool.py',),), cwd=self.ks_dir)
        subprocess.check_call(("git", "config", "--add",
                               "mergetool.git-sort.trustexitcode", "true",), cwd=self.ks_dir)
        retval = subprocess.call(("git", "merge", "other",), cwd=self.ks_dir,
                                       stdout=subprocess.DEVNULL,
                                       stderr=subprocess.DEVNULL)
        self.assertEqual(retval, 1)
        retval = subprocess.check_output(
            ("git", "mergetool", "--tool=git-sort", "series.conf",), cwd=self.ks_dir)
        self.assertEqual(
            retval.decode().splitlines()[-1].strip(),
            "1 commits added, 0 commits removed from base to remote.")
        with (self.ks_dir / 'series.conf').open() as f:
            entries = series_conf.filter_series(f.readlines())
        self.assertEqual(entries,
                         ["patches.suse/%s.patch" %
                          (tests.support.format_sanitized_subject(
                              self.repo.get(commit).message),)
                          for commit in self.commits[:4]])
        retval = subprocess.check_output(("git", "status", "--porcelain",
                                          "series.conf",), cwd=self.ks_dir)
        self.assertEqual(retval.decode().strip(), "M  series.conf")


@unittest.skip("Patched quilt not maintained")
class TestQCP(unittest.TestCase):
    def setUp(self):
        os.environ["XDG_CACHE_HOME"] = tempfile.mkdtemp(prefix="gs_cache")

        # setup stub linux repository
        os.environ["LINUX_GIT"] = tempfile.mkdtemp(prefix="gs_repo")
        self.repo = pygit2.init_repository(os.environ["LINUX_GIT"])
        self.repo.config["user.email"] = "author1@example.com"
        self.repo.config["user.name"] = "Author One"

        author = pygit2.Signature("Author One", "author1@example.com")
        committer = pygit2.Signature("Maintainer One", "maintainer1@example.com")
        tree = self.repo.TreeBuilder()

        tree.insert("driver.c", 
                    self.repo.create_blob("#include <bad.h>\n"),
                    pygit2.GIT_FILEMODE_BLOB)
        self.commits = []
        self.commits.append(self.repo.create_commit(
            "refs/heads/mainline",
            author,
            committer,
            """Add a very small module

... which was not tested.

Signed-off-by: Author One <author1@example.com>
Signed-off-by: Maintainer One <maintainer@example.com>
""",
            tree.write(),
            []
        ))

        tree.insert("driver.c", 
                    self.repo.create_blob("#include <linux/module.h>\n"),
                    pygit2.GIT_FILEMODE_BLOB)
        self.commits.append(self.repo.create_commit(
            "refs/heads/mainline",
            author,
            committer,
            """Fix the very small module

syzbot is reporting deadlocks at __blkdev_get() [1].

----------------------------------------
[   92.493919] systemd-udevd   D12696   525      1 0x00000000
[   92.495891] Call Trace:
[   92.501560]  schedule+0x23/0x80
[   92.502923]  schedule_preempt_disabled+0x5/0x10
[   92.504645]  __mutex_lock+0x416/0x9e0
[   92.510760]  __blkdev_get+0x73/0x4f0
[   92.512220]  blkdev_get+0x12e/0x390
[   92.518151]  do_dentry_open+0x1c3/0x2f0
[   92.519815]  path_openat+0x5d9/0xdc0
[   92.521437]  do_filp_open+0x7d/0xf0
[   92.527365]  do_sys_open+0x1b8/0x250
[   92.528831]  do_syscall_64+0x6e/0x270
[   92.530341]  entry_SYSCALL_64_after_hwframe+0x42/0xb7

[   92.931922] 1 lock held by systemd-udevd/525:
[   92.933642]  #0: 00000000a2849e25 (&bdev->bd_mutex){+.+.}, at: __blkdev_get+0x73/0x4f0
----------------------------------------

The reason of deadlock turned out that wait_event_interruptible() in

Reported-by: Markus Trippelsdorf <markus@trippelsdorf.de>
Fixes: %s ("Add a very small module")
Signed-off-by: Author One <author1@example.com>
Signed-off-by: Maintainer One <maintainer@example.com>
""" % (str(self.commits[-1],)),
            tree.write(),
            [self.commits[-1]]
        ))

        self.repo.create_tag("v4.10-rc6", self.commits[-1], pygit2.GIT_REF_OID,
                             committer, "Linux 4.10-rc6")

        self.repo.remotes.create(
            "origin",
            "git://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git")
        self.repo.references.create("refs/remotes/origin/master",
                                    self.commits[-1])

        # setup stub kernel-source content
        self.ks_dir = Path(tempfile.mkdtemp(prefix="gs_ks"))
        patch_dir = self.ks_dir / 'patches.suse'
        patch_dir.mkdir()
        with (self.ks_dir / "series.conf").open('w') as f:
            f.write(
"""# Kernel patches configuration file

	########################################################
	# sorted patches
	########################################################
""")
            f.write("\tpatches.suse/%s\n" % (
                tests.support.format_patch(self.repo.get(self.commits[0]),
                                           mainline="v4.9",
                                           directory=patch_dir,
                                           references="bsc#123").relative_to(patch_dir),))
            f.write(
"""
	########################################################
	# end of sorted patches
	########################################################
""")

        # This overlaps what is tested by test_series_sort, hence, not put in a
        # test of its own.
        subprocess.check_call([lib.ss_path, '-c', 'series.conf'], cwd=self.ks_dir)
        content1 = (self.ks_dir / 'series.conf').read_text()
        subprocess.check_call([lib.ss_path, 'series.conf'], cwd=self.ks_dir)
        content2 = (self.ks_dir / 'series.conf').read_text()
        self.assertEqual(content2, content1)

        self.current = self.ks_dir / 'tmp/current'
        self.current.mkdir(parents=True)
        subprocess.check_call(
            ["quilt", "setup", "--sourcedir", "../../", "../../series.conf"], cwd=self.current)


    def tearDown(self):
        shutil.rmtree(os.environ["XDG_CACHE_HOME"])
        shutil.rmtree(os.environ["LINUX_GIT"])
        shutil.rmtree(self.ks_dir)


    def test_fixup(self):

        # import commits[1]
        subprocess.check_call(
            ". %s; qgoto %s" % (lib.qm_path, str(self.commits[1])), shell=True,
            cwd=self.current, stdout=subprocess.DEVNULL, executable="/bin/bash")
        subprocess.check_call(
            """. %s; qcp -f %s""" % (
                lib.qm_path, str(self.commits[1])),
            cwd=self.current, shell=True, stdout=subprocess.DEVNULL, executable="/bin/bash")

        retval = subprocess.check_output(("quilt", "--quiltrc", "-", "next",), cwd=self.current)
        name = "patches.suse/Fix-the-very-small-module.patch"
        self.assertEqual(retval.decode().strip(), name)


if __name__ == '__main__':
    # Run a single testcase
    suite = unittest.TestLoader().loadTestsFromTestCase(TestQCP)
    unittest.TextTestRunner(verbosity=2).run(suite)
