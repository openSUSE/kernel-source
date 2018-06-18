#!/usr/bin/python3
# -*- coding: utf-8 -*-

import os.path
import shutil
import subprocess
import tempfile
import unittest
import stat
import sys

import lib


class TestSpliceSeries(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.covdir = tempfile.mkdtemp(prefix="gs_log2_cov")


    @classmethod
    def tearDownClass(cls):
        print("Coverage report in %s. Press enter when done with it." %
              (cls.covdir,))
        sys.stdin.readline()
        shutil.rmtree(cls.covdir)


    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="gs_log2")
        os.chdir(self.tmpdir)
        self.log2_path = os.path.join( lib.libdir(), "../log2")


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
                with open("old", mode="w") as f:
                    f.write(old)

                with open("new", mode="w") as f:
                    f.write(new)

                with open("test.sh", mode="w") as f:
                    f.write(
                        """#!/bin/bash

                        . %s
                        splice_series %s 3<old 4<new\n""" % (
                            self.log2_path, patch,))
                os.chmod("test.sh", stat.S_IRWXU)

                sp = subprocess.Popen(
                    ["kcov", "--include-path=%s" % (self.log2_path,),
                     self.__class__.covdir, "test.sh"],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
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
                with open("old", mode="w") as f:
                    f.write(old)

                with open("new", mode="w") as f:
                    f.write(new)

                with open("test.sh", mode="w") as f:
                    f.write(
                        """#!/bin/bash

                        . %s
                        splice_series %s 3<old 4<new\n""" % (
                            self.log2_path, patch,))
                os.chmod("test.sh", stat.S_IRWXU)

                retval = subprocess.check_output(
                    ["kcov", "--include-path=%s" % (self.log2_path,),
                     self.__class__.covdir, "test.sh"])
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
                with open("old", mode="w") as f:
                    f.write(old)

                with open("new", mode="w") as f:
                    f.write(new)

                with open("test.sh", mode="w") as f:
                    f.write(
                        """#!/bin/bash

                        . %s
                        splice_series %s 3<old 4<new\n""" % (
                            self.log2_path, patch,))
                os.chmod("test.sh", stat.S_IRWXU)

                retval = subprocess.check_output(
                    ["kcov", "--include-path=%s" % (self.log2_path,),
                     self.__class__.covdir, "test.sh"])
                self.assertEqual(intermediate, retval.decode())


if __name__ == '__main__':
    # Run a single testcase
    suite = unittest.TestLoader().loadTestsFromTestCase(TestSpliceSeries)
    unittest.TextTestRunner(verbosity=2).run(suite)
