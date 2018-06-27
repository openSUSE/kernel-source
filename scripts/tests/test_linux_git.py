#!/usr/bin/python3
# -*- coding: utf-8 -*-

import os.path
import shutil
import subprocess
import tempfile
import unittest

import lib


class TestLinuxGit(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="ks_linux_git")
        self.lg_path = os.path.join(lib.libdir(), "../linux_git.sh")


    def tearDown(self):
        shutil.rmtree(self.tmpdir)


    def run_one(self, bare, var, output):
        args = ["git", "init", "--quiet"]
        if bare:
            args.append("--bare")
        args.append(self.tmpdir)

        subprocess.check_call(args, env={})

        retval = subprocess.check_output((self.lg_path,),
                                         env={"LINUX_GIT" : var})
        self.assertEqual(output, retval.decode())


    def test_bare(self):
        self.run_one(True, self.tmpdir, self.tmpdir + "\n")


    def test_nonbare(self):
        "Test non --bare repo with and without .git component in env var"
        self.run_one(False, self.tmpdir, os.path.join(self.tmpdir, ".git") + "\n")
        self.run_one(False, os.path.join(self.tmpdir, ".git"),
                     os.path.join(self.tmpdir, ".git") + "\n")


if __name__ == '__main__':
    # Run a single testcase
    suite = unittest.TestLoader().loadTestsFromTestCase(TestLinuxGit)
    unittest.TextTestRunner(verbosity=2).run(suite)
