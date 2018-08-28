#!/usr/bin/python3
# -*- coding: utf-8 -*-

import os
import os.path
import pygit2
import shutil
import subprocess
import sys
import tempfile
import unittest

import git_sort
import lib
import series_conf
import tests.support


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
        self.ks_dir = tempfile.mkdtemp(prefix="gs_ks")
        patch_dir = os.path.join(self.ks_dir, "patches.suse")
        os.mkdir(patch_dir)
        os.chdir(patch_dir)
        with open(os.path.join(self.ks_dir, "series.conf"), mode="w") as f:
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
                                               mainline=tag),))
            f.write(
"""
	########################################################
	# end of sorted patches
	########################################################
""")

        ss_path = os.path.join(lib.libdir(), "series_sort.py")
        os.chdir(self.ks_dir)

        # This overlaps what is tested by test_series_sort, hence, not put in a
        # test of its own.
        subprocess.check_call([ss_path, "-c", "series.conf"])
        with open("series.conf") as f:
            content1 = f.read()
        subprocess.check_call([ss_path, "series.conf"])
        with open("series.conf") as f:
            content2 = f.read()
        self.assertEqual(content2, content1)

        subprocess.check_call(("git", "init", "./",), stdout=subprocess.DEVNULL)
        subprocess.check_call(("git", "add", "series.conf", "patches.suse",),
                              stdout=subprocess.DEVNULL)
        subprocess.check_call(("git", "commit", "-m", "import",),
                              stdout=subprocess.DEVNULL)

        os.makedirs("tmp/current")
        os.chdir("tmp/current")
        subprocess.check_call(
            ["quilt", "setup", "--sourcedir", "../../", "../../series.conf"])


    def tearDown(self):
        shutil.rmtree(os.environ["XDG_CACHE_HOME"])
        shutil.rmtree(os.environ["LINUX_GIT"])
        shutil.rmtree(self.ks_dir)


    def test_quilt_mode(self):
        qm_path = os.path.join(lib.libdir(), "quilt-mode.sh")

        # test series file replacement
        with open("series") as f:
            entries = ["%s\n" % (l,) for l in
                       [line.strip() for line in f.readlines()]
                       if l and not l.startswith("#")]
        # remove the symlink
        os.unlink("series")
        with open("series", mode="w") as f:
            f.writelines(entries)
        subprocess.check_call(
            (os.path.join(lib.libdir(), "qgoto.py"), str(self.commits[0]),),
            stdout=subprocess.DEVNULL)

        # test qgoto
        subprocess.check_call(
            ". %s; qgoto %s" % (qm_path, str(self.commits[0])), shell=True,
            stdout=subprocess.DEVNULL, executable="/bin/bash")

        # test qdupcheck
        try:
            subprocess.check_output(
                ". %s; qdupcheck %s" % (qm_path, str(self.commits[1])),
                shell=True, executable="/bin/bash")
        except subprocess.CalledProcessError as err:
            self.assertEqual(err.returncode, 1)
            self.assertEqual(err.output.decode().splitlines()[-1].strip(),
                             "patches.suse/Linux-4.10-rc5.patch")
        else:
            self.assertTrue(False)
        
        subprocess.check_call(
            ". %s; qgoto %s" % (qm_path, str(self.commits[1])), shell=True,
            stdout=subprocess.DEVNULL, executable="/bin/bash")

        try:
            subprocess.check_output(
                ". %s; qdupcheck %s" % (qm_path, str(self.commits[1])),
                shell=True, executable="/bin/bash")
        except subprocess.CalledProcessError as err:
            self.assertEqual(err.returncode, 1)
            self.assertEqual(err.output.decode().splitlines()[-1].strip(),
                             "This is the top patch.")
        else:
            self.assertTrue(False)

        # import commits[2]
        subprocess.check_call(
            ". %s; qgoto %s" % (qm_path, str(self.commits[2])), shell=True,
            executable="/bin/bash")
        subprocess.check_call(
            """. %s; qcp -r "bsc#1077761" -d patches.suse %s""" % (
                qm_path, str(self.commits[2])),
            shell=True, stdout=subprocess.DEVNULL, executable="/bin/bash")

        retval = subprocess.check_output(("quilt", "--quiltrc", "-", "next",))
        name = "patches.suse/KVM-arm-arm64-vgic-v3-Add-accessors-for-the-ICH_APxR.patch"
        self.assertEqual(retval.decode().strip(), name)

        try:
            with open(os.path.join(self.ks_dir, name)) as f:
                retval = f.readlines().index(
                    "Acked-by: Alexander Graf <agraf@suse.de>\n")
        except ValueError:
            retval = -1
        self.assertNotEqual(retval, -1)

        subprocess.check_call(("quilt", "--quiltrc", "-", "push",),
                              stdout=subprocess.DEVNULL)

        try:
            subprocess.check_output(("quilt", "--quiltrc", "-", "pop",),
                                    stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError as err:
            self.assertEqual(err.returncode, 1)
            self.assertTrue(err.output.decode().endswith(
                "needs to be refreshed first.\n"))
        else:
            self.assertTrue(False)

        subprocess.check_call(("quilt", "--quiltrc", "-", "refresh",),
                              stdout=subprocess.DEVNULL)
        subprocess.check_call(("quilt", "--quiltrc", "-", "pop",),
                              stdout=subprocess.DEVNULL)
        subprocess.check_call(("quilt", "--quiltrc", "-", "push",),
                              stdout=subprocess.DEVNULL)

        # prepare repository
        os.chdir(self.ks_dir)
        subprocess.check_call(("git", "add", "series.conf", "patches.suse",),
                       stdout=subprocess.DEVNULL)
        subprocess.check_call(
            ("git", "commit", "-m",
             "KVM: arm/arm64: vgic-v3: Add accessors for the ICH_APxRn_EL2 registers",),
            stdout=subprocess.DEVNULL)
        subprocess.check_call(("git", "checkout", "-q", "-b", "other",
                               "HEAD^",))
        shutil.rmtree("tmp/current")
        os.makedirs("tmp/current")
        os.chdir("tmp/current")
        subprocess.check_call(("quilt", "setup", "--sourcedir", "../../",
                               "../../series.conf",),)

        # import commits[3]
        subprocess.check_call(
            ". %s; qgoto %s" % (qm_path, str(self.commits[3])), shell=True,
            stdout=subprocess.DEVNULL, executable="/bin/bash")
        subprocess.check_call(
            """. %s; qcp -r "bsc#123" -d patches.suse %s""" % (
                qm_path, str(self.commits[3])),
            shell=True, stdout=subprocess.DEVNULL, executable="/bin/bash")

        subprocess.check_call(("quilt", "--quiltrc", "-", "push",),
                              stdout=subprocess.DEVNULL)
        subprocess.check_call(("quilt", "--quiltrc", "-", "refresh",),
                              stdout=subprocess.DEVNULL)
        name = subprocess.check_output(
            ("quilt", "--quiltrc", "-", "top",)).decode().strip()

        os.chdir(self.ks_dir)
        subprocess.check_call(("git", "add", "series.conf", "patches.suse",),
                              stdout=subprocess.DEVNULL)

        # test pre-commit.sh
        pc_path = os.path.join(lib.libdir(), "pre-commit.sh")

        subprocess.check_call(pc_path, stdout=subprocess.DEVNULL)

        with open("series.conf") as f:
            content = f.readlines()

        content2 = list(content)
        middle = int(len(content2) / 2)
        content2[middle], content2[middle + 1] = \
            content2[middle + 1], content2[middle]

        with open("series.conf", mode="w") as f:
            f.writelines(content2)

        # check should be done against index, not working tree
        subprocess.check_call(pc_path, stdout=subprocess.DEVNULL)

        subprocess.check_call(("git", "add", "series.conf",),
                              stdout=subprocess.DEVNULL)

        # ... test a bad sorted section
        try:
            subprocess.check_output(pc_path, stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError as err:
            self.assertEqual(err.returncode, 1)
            self.assertTrue(err.output.decode().startswith(
                "Input is not sorted."))
        else:
            self.assertTrue(False)

        with open("series.conf", mode="w") as f:
            f.writelines(content)

        subprocess.check_call(("git", "add", "series.conf",),
                              stdout=subprocess.DEVNULL)

        subprocess.check_call(("git", "commit", "-m",
                               "sched/debug: Ignore TASK_IDLE for SysRq-W",),
                              stdout=subprocess.DEVNULL)

        # ... test a bad sorted patch
        with open(name) as f:
            content = f.readlines()
        content2 = list(content)
        for i in range(len(content2)):
            if content2[i].startswith("Git-commit: "):
                content2[i] = "Git-commit: cb329c2e40cf6cfc7bcd7c36ce5547f95e972ea5\n"
                break
        with open(name, mode="w") as f:
            f.writelines(content2)
        subprocess.check_call(("git", "add", name,), stdout=subprocess.DEVNULL)

        try:
            subprocess.check_output(pc_path, stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError as err:
            self.assertEqual(err.returncode, 1)
            self.assertTrue(err.output.decode().startswith(
                "Error: There is a problem with patch \"%s\"." % (name,)))
        else:
            self.assertTrue(False)

        with open(name, mode="w") as f:
            f.writelines(content)
        subprocess.check_call(("git", "add", name,), stdout=subprocess.DEVNULL)

        # test merge_tool.py
        subprocess.check_call(("git", "checkout", "-q", "master",))
        shutil.rmtree("tmp/current")
        subprocess.check_call(
            ("git", "config", "--add", "mergetool.git-sort.cmd",
             "%s $LOCAL $BASE $REMOTE $MERGED" % (
                 os.path.join(lib.libdir(), "merge_tool.py"),),))
        subprocess.check_call(("git", "config", "--add",
                               "mergetool.git-sort.trustexitcode", "true",))
        retval = subprocess.call(("git", "merge", "other",),
                                       stdout=subprocess.DEVNULL,
                                       stderr=subprocess.DEVNULL)
        self.assertEqual(retval, 1)
        retval = subprocess.check_output(
            ("git", "mergetool", "--tool=git-sort", "series.conf",))
        self.assertEqual(
            retval.decode().splitlines()[-1].strip(),
            "1 commits added, 0 commits removed from base to remote.")
        with open("series.conf") as f:
            entries = series_conf.filter_series(f.readlines())
        self.assertEqual(entries,
                         ["patches.suse/%s.patch" %
                          (tests.support.format_sanitized_subject(
                              self.repo.get(commit).message),)
                          for commit in self.commits[:4]])
        retval = subprocess.check_output(("git", "status", "--porcelain",
                                          "series.conf",))
        self.assertEqual(retval.decode().strip(), "M  series.conf")


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

        subprocess.check_call(("git", "init", "./",), stdout=subprocess.DEVNULL)
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
        self.ks_dir = tempfile.mkdtemp(prefix="gs_ks")
        patch_dir = os.path.join(self.ks_dir, "patches.suse")
        os.mkdir(patch_dir)
        os.chdir(patch_dir)
        with open(os.path.join(self.ks_dir, "series.conf"), mode="w") as f:
            f.write(
"""# Kernel patches configuration file

	########################################################
	# sorted patches
	########################################################
""")
            f.write("\tpatches.suse/%s\n" % (
                tests.support.format_patch(self.repo.get(self.commits[0]),
                                           mainline="v4.9",
                                           references="bsc#123"),))
            f.write(
"""
	########################################################
	# end of sorted patches
	########################################################
""")

        ss_path = os.path.join(lib.libdir(), "series_sort.py")
        os.chdir(self.ks_dir)

        # This overlaps what is tested by test_series_sort, hence, not put in a
        # test of its own.
        subprocess.check_call([ss_path, "-c", "series.conf"])
        with open("series.conf") as f:
            content1 = f.read()
        subprocess.check_call([ss_path, "series.conf"])
        with open("series.conf") as f:
            content2 = f.read()
        self.assertEqual(content2, content1)

        os.makedirs("tmp/current")
        os.chdir("tmp/current")
        subprocess.check_call(
            ["quilt", "setup", "--sourcedir", "../../", "../../series.conf"])


    def tearDown(self):
        shutil.rmtree(os.environ["XDG_CACHE_HOME"])
        shutil.rmtree(os.environ["LINUX_GIT"])
        shutil.rmtree(self.ks_dir)


    def test_fixup(self):
        qm_path = os.path.join(lib.libdir(), "quilt-mode.sh")

        # import commits[1]
        subprocess.check_call(
            ". %s; qgoto %s" % (qm_path, str(self.commits[1])), shell=True,
            stdout=subprocess.DEVNULL, executable="/bin/bash")
        subprocess.check_call(
            """. %s; qcp -f %s""" % (
                qm_path, str(self.commits[1])),
            shell=True, stdout=subprocess.DEVNULL, executable="/bin/bash")

        retval = subprocess.check_output(("quilt", "--quiltrc", "-", "next",))
        name = "patches.suse/Fix-the-very-small-module.patch"
        self.assertEqual(retval.decode().strip(), name)


if __name__ == '__main__':
    # Run a single testcase
    suite = unittest.TestLoader().loadTestsFromTestCase(TestQCP)
    unittest.TextTestRunner(verbosity=2).run(suite)
