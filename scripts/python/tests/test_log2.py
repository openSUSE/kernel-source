#!/usr/bin/python3
# -*- coding: utf-8 -*-

from pathlib import Path
import subprocess
import tempfile
import unittest
import shutil
import stat
import sys
import os

from . import support


class TestSpliceSeries(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.covdir = tempfile.mkdtemp(prefix="gs_log2_cov")
        cls.kcov = shutil.which('kcov')
        if not cls.kcov:
            sys.stderr.write("kcov is not available\n")


    @classmethod
    def tearDownClass(cls):
        if cls.kcov and os.isatty(sys.stdin.fileno()):
            print("Coverage report in %s Press enter when done with it." %
                  (cls.covdir,))
            sys.stdin.readline()
        shutil.rmtree(cls.covdir)


    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="gs_log2"))
        self.log2_path = support.testdir() / '../../log2'
        self.cmd = ['./test.sh']
        if self.kcov:
            self.cmd = [self.kcov, "--include-path=%s" % (self.log2_path,),
                        self.covdir] + self.cmd
        self.testscript = """#!/bin/bash

                          . %s
                          splice_series %%s 3<old 4<new\n""" % (
                                  self.log2_path,)


    def tearDown(self):
        shutil.rmtree(self.tmpdir)


    def test_errors(self):
        vectors = (
            # missing in matching
            (
"""	patches.fixes/0
	patches.fixes/1
	patches.fixes/2
""",
"""	patches.fixes/0
	patches.fixes/1
""",
                "patches.fixes/3",
                "Error: new series does not contain all lines from old "
                "series.\n",
            ),
            # missing in diff
            (
"""	patches.fixes/0
	patches.fixes/1
	patches.fixes/2
""",
"""	patches.fixes/0
	patches.fixes/2
	patches.fixes/3
""",
                "patches.fixes/4",
                "Error: new series does not contain all lines from old "
                "series.\n",
            ),
            # patch not found
            (
"""	patches.fixes/0
	patches.fixes/1
	patches.fixes/2
""",
"""	patches.fixes/0
	patches.fixes/1
	patches.fixes/2
""",
                "patches.fixes/3",
                "Error: patch \"patches.fixes/3\" not found in series.\n",
            ),
        )

        for i in range(len(vectors)):
            old, new, patch, msg = vectors[i]
            with self.subTest(vector=i):
                (self.tmpdir / 'old').write_text(old)
                (self.tmpdir / 'new').write_text(new)
                (self.tmpdir / 'test.sh').write_text(self.testscript % (patch,))
                (self.tmpdir / 'test.sh').chmod(stat.S_IRWXU)

                sp = subprocess.Popen(self.cmd,
                    cwd=self.tmpdir, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                out, err = sp.communicate()
                retval = sp.wait()

                self.assertEqual(retval, 1)
                self.assertEqual(msg, err.decode())


    def test_simple(self):
        vectors = (
            # append
            (
"""	patches.fixes/0
	patches.fixes/1
	patches.fixes/2
""",
"""	patches.fixes/0
	patches.fixes/1
	patches.fixes/2
	patches.fixes/3
""",
                "patches.fixes/3",),
            # append
            (
"""	patches.fixes/0
	patches.fixes/1
	patches.fixes/2

""",
"""	patches.fixes/0
	patches.fixes/1
	patches.fixes/2
	patches.fixes/3

""",
                "patches.fixes/3",),
            # prepend
            (
"""	patches.fixes/1
	patches.fixes/2
	patches.fixes/3
""",
"""	patches.fixes/0
	patches.fixes/1
	patches.fixes/2
	patches.fixes/3
""",
                "patches.fixes/0",),
            # insert
            (
"""	patches.fixes/0
	patches.fixes/2
	patches.fixes/3
""",
"""	patches.fixes/0
	patches.fixes/1
	patches.fixes/2
	patches.fixes/3
""",
                "patches.fixes/1",),
            # with sections
            (
"""	patches.fixes/0
	
	# jejb/scsi for-next
	patches.fixes/1
	patches.fixes/3
""",
"""	patches.fixes/0
	
	# jejb/scsi for-next
	patches.fixes/1
	patches.fixes/2
	patches.fixes/3
""",
                "patches.fixes/2",),
            # add section
            (
"""	patches.fixes/0
""",
"""	patches.fixes/0
	
	# jejb/scsi for-next
	patches.fixes/1
""",
            "patches.fixes/1",),
        )

        for i in range(len(vectors)):
            old, new, patch = vectors[i]
            with self.subTest(vector=i):
                (self.tmpdir / 'old').write_text(old)
                (self.tmpdir / 'new').write_text(new)
                (self.tmpdir / 'test.sh').write_text(self.testscript % (patch,))
                (self.tmpdir / 'test.sh').chmod(stat.S_IRWXU)

                retval = subprocess.check_output(self.cmd, cwd=self.tmpdir)
                self.assertEqual(new, retval.decode())


    def test_intermediate(self):
        vectors = (
            # start of new section
            (
"""	patches.fixes/0
	
	# out-of-tree patches
	patches.drivers/0
	patches.drivers/1
""",
"""	patches.fixes/0
	
	# jejb/scsi for-next
	patches.fixes/1
	patches.fixes/2
	
	# out-of-tree patches
	patches.drivers/0
	patches.drivers/1
""",
                "patches.fixes/1",
"""	patches.fixes/0
	
	# jejb/scsi for-next
	patches.fixes/1
	
	# out-of-tree patches
	patches.drivers/0
	patches.drivers/1
""",),
            # end of new section
            (
"""	patches.fixes/0
	
	# out-of-tree patches
	patches.drivers/0
	patches.drivers/1
""",
"""	patches.fixes/0
	
	# jejb/scsi for-next
	patches.fixes/1
	patches.fixes/2
	
	# out-of-tree patches
	patches.drivers/0
	patches.drivers/1
""",
                "patches.fixes/2",
"""	patches.fixes/0
	
	# jejb/scsi for-next
	patches.fixes/1
	patches.fixes/2
	
	# out-of-tree patches
	patches.drivers/0
	patches.drivers/1
""",),
            # middle of new section
            (
"""	patches.fixes/0
	
	# out-of-tree patches
	patches.drivers/0
	patches.drivers/1
""",
"""	patches.fixes/0
	
	# jejb/scsi for-next
	patches.fixes/1
	patches.fixes/2
	patches.fixes/3
	
	# out-of-tree patches
	patches.drivers/0
	patches.drivers/1
""",
                "patches.fixes/2",
"""	patches.fixes/0
	
	# jejb/scsi for-next
	patches.fixes/1
	patches.fixes/2
	
	# out-of-tree patches
	patches.drivers/0
	patches.drivers/1
""",),
            # end of existing section
            (
"""	patches.fixes/0
	
	# jejb/scsi for-next
	patches.fixes/1
	
	# out-of-tree patches
	patches.drivers/0
	patches.drivers/1
""",
"""	patches.fixes/0
	
	# jejb/scsi for-next
	patches.fixes/1
	patches.fixes/2
	patches.fixes/3
	
	# out-of-tree patches
	patches.drivers/0
	patches.drivers/1
""",
                "patches.fixes/2",
"""	patches.fixes/0
	
	# jejb/scsi for-next
	patches.fixes/1
	patches.fixes/2
	
	# out-of-tree patches
	patches.drivers/0
	patches.drivers/1
""",),
            (
"""	patches.fixes/0
	
	# jejb/scsi for-next
	patches.fixes/1
	
	# out-of-tree patches
	patches.drivers/0
	patches.drivers/1
""",
"""	patches.fixes/0
	
	# jejb/scsi for-next
	patches.fixes/1
	patches.fixes/2
	patches.fixes/3
	
	# out-of-tree patches
	patches.drivers/0
	patches.drivers/1
""",
                "patches.fixes/3",
"""	patches.fixes/0
	
	# jejb/scsi for-next
	patches.fixes/1
	patches.fixes/2
	patches.fixes/3
	
	# out-of-tree patches
	patches.drivers/0
	patches.drivers/1
""",),
            # spread in different places
            (
"""	patches.fixes/0
	
	# jejb/scsi for-next
	patches.fixes/2
	
	# out-of-tree patches
	patches.drivers/0
	patches.drivers/1
""",
"""	patches.fixes/0
	patches.fixes/1
	
	# jejb/scsi for-next
	patches.fixes/2
	patches.fixes/3
	
	# out-of-tree patches
	patches.drivers/0
	patches.drivers/1
""",
                "patches.fixes/1",
"""	patches.fixes/0
	patches.fixes/1
	
	# jejb/scsi for-next
	patches.fixes/2
	
	# out-of-tree patches
	patches.drivers/0
	patches.drivers/1
""",),
            (
"""	patches.fixes/0
	
	# jejb/scsi for-next
	patches.fixes/2
	
	# out-of-tree patches
	patches.drivers/0
	patches.drivers/1
""",
"""	patches.fixes/0
	patches.fixes/1
	
	# jejb/scsi for-next
	patches.fixes/2
	patches.fixes/3
	
	# out-of-tree patches
	patches.drivers/0
	patches.drivers/1
""",
                "patches.fixes/3",
"""	patches.fixes/0
	patches.fixes/1
	
	# jejb/scsi for-next
	patches.fixes/2
	patches.fixes/3
	
	# out-of-tree patches
	patches.drivers/0
	patches.drivers/1
""",),
            # two new sections
            (
"""	patches.fixes/0

	# out-of-tree patches
	patches.suse/0
	patches.suse/1
""",
"""	patches.fixes/0

	# davem/net
	patches.drivers/1
	patches.drivers/2

	# davem/net-next
	patches.drivers/3
	patches.drivers/4

	# out-of-tree patches
	patches.suse/0
	patches.suse/1
""",
                "patches.drivers/1",
"""	patches.fixes/0

	# davem/net
	patches.drivers/1

	# out-of-tree patches
	patches.suse/0
	patches.suse/1
""",),
            # eof in whitespace
            (
"""	patches.fixes/0
""",
"""	patches.fixes/0

	# davem/net
	patches.drivers/1
	patches.drivers/2

""",
                "patches.drivers/1",
"""	patches.fixes/0

	# davem/net
	patches.drivers/1

""",),
            # two new sections, multi-line whitespace
            (
"""	patches.fixes/0

	# out-of-tree patches
	patches.suse/0
	patches.suse/1
""",
"""	patches.fixes/0

	# davem/net
	patches.drivers/1
	patches.drivers/2


	# davem/net-next
	patches.drivers/3
	patches.drivers/4

	# out-of-tree patches
	patches.suse/0
	patches.suse/1
""",
                "patches.drivers/1",
"""	patches.fixes/0

	# davem/net
	patches.drivers/1


	# out-of-tree patches
	patches.suse/0
	patches.suse/1
""",),
            # two new sections, eof in new
            (
"""	patches.fixes/0
""",
"""	patches.fixes/0

	# davem/net
	patches.drivers/1
	patches.drivers/2

	# davem/net-next
	patches.drivers/3
	patches.drivers/4
""",
                "patches.drivers/1",
"""	patches.fixes/0

	# davem/net
	patches.drivers/1

""",),
            )

        for i in range(len(vectors)):
            old, new, patch, intermediate = vectors[i]
            with self.subTest(vector=i):
                (self.tmpdir / 'old').write_text(old)
                (self.tmpdir / 'new').write_text(new)
                (self.tmpdir / 'test.sh').write_text(self.testscript % (patch,))
                (self.tmpdir / 'test.sh').chmod(stat.S_IRWXU)

                retval = subprocess.check_output(self.cmd, cwd=self.tmpdir)
                self.assertEqual(intermediate, retval.decode())


if __name__ == '__main__':
    # Run a single testcase
    suite = unittest.TestLoader().loadTestsFromTestCase(TestSpliceSeries)
    unittest.TextTestRunner(verbosity=2).run(suite)
