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
        readme_path = os.path.join(os.environ["LINUX_GIT"], "README")

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

        #sys.stdin.readline()


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

        # test merge_tool.py
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
        # ... import commits[3]
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

        os.chdir(self.ks_dir)
        subprocess.check_call(("git", "add", "series.conf", "patches.suse",),
                              stdout=subprocess.DEVNULL)
        subprocess.check_call(("git", "commit", "-m",
                               "sched/debug: Ignore TASK_IDLE for SysRq-W",),
                              stdout=subprocess.DEVNULL)

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

if __name__ == '__main__':
    # Run a single testcase
    suite = unittest.TestLoader().loadTestsFromTestCase(TestQuiltMode)
    unittest.TextTestRunner(verbosity=2).run(suite)
