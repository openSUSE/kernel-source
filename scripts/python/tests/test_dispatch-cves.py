#!/usr/bin/python3
# -*- coding: utf-8 -*-

from xmlrpc.client import DateTime
import tempfile
import unittest
import sys

if sys.version_info.major != 3 or sys.version_info.minor > 5:
    from cve_tools import dispatch_cves

class DictObj:
    def __init__(self, kw):
        self.update(kw)

    def update(self, kw):
        for k, v in kw.items():
            setattr(self, k, v)

class BZMock:
    def __init__(self):
        self.logged_in = True
        self.updates = dict()
        self.mockbugs = list()

    def getbugs(self, *args, **kwargs):
        return self.mockbugs

    def get_comments(self, *args, **kwargs):
        no_comments = {str(b.id): {'comments': []} for b in self.mockbugs}
        return {'bugs': no_comments}


    def build_update(self, *args, **fields):
        ret = dict(fields)
        ret.update({'stamp': True})
        return ret

    def update_bugs(self, ids, fields):
        for id in ids:
            self.updates[id] = fields


@unittest.skipIf(sys.version_info.major == 3 and sys.version_info.minor < 6, "python before 3.6 not supported")
class TestDispatchCves(unittest.TestCase):
    def setUp(self):
        self.bzapi = BZMock()

        inputs = ["""
Security fix for CVE-2026-53035 bsc#1269190 with CVSS 5.5
ASSIGNEE: mkoutny@suse.com
CC: mkoutny@suse.com

NO ACTION NEEDED
""",
                  """
Security fix for CVE-2026-53035 bsc#1269190 with CVSS 7.0
ASSIGNEE: mkoutny@suse.com
CC: mkoutny@suse.com

NO ACTION NEEDED
""",
                  ]
        self.mockfiles = []
        for i in inputs:
            file = tempfile.NamedTemporaryFile('w', encoding='utf-8')
            file.write(i.lstrip())
            file.flush()
            self.mockfiles.append(file)

        self.bzapi.mockbugs.append(DictObj({
            'id': 1269190,
            'alias': 'CVE-2026-53035',
            'assigned_to': 'not.mkoutny@suse.com',
            'cc': [],
            'flags': [],
            'product': 'SUSE Security Incidents',
            'creation_time': DateTime('20260625T15:30:48'),
            }))


    def tearDown(self):
        for f in self.mockfiles:
            f.close()


    def test_single_dispatch(self):
        self.bzapi.mockbugs[0].update({
            'assigned_to': 'kernel-bugs@suse.de',
        })

        ret = dispatch_cves.single_dispatch(
                self.bzapi,
                self.mockfiles[0].name,
                False,
                True, # yes
                False,
                None,
                False
                )
        self.assertEqual(ret, None)
        self.assertIn(1269190, self.bzapi.updates)
        self.assertEqual(self.bzapi.updates[1269190]['comment'],
                         'Security fix for CVE-2026-53035 bsc#1269190 with CVSS 5.5\n\nNO ACTION NEEDED\n')
        self.assertEqual(self.bzapi.updates[1269190]['assigned_to'],
                         'kernel-security-sentinel@lists.suse.com') # because no force
        self.assertIn('mkoutny@suse.com', self.bzapi.updates[1269190]['cc_add'])

    def test_single_dispatch_deadline(self):
        for creation, exp_deadline, file_idx in [
                ('20260625T15:30:48', '2026-09-01', 0),
                ('20260625T15:30:48', '2026-08-01', 1),
                ]:
            with self.subTest("Interval {}-{}".format(creation, exp_deadline)):
                self.bzapi.mockbugs[0].update({
                    'assigned_to': 'kernel-bugs@suse.de',
                    'creation_time': DateTime(creation),
                })

                ret = dispatch_cves.single_dispatch(
                        self.bzapi,
                        self.mockfiles[file_idx].name,
                        False,
                        True, # yes
                        False,
                        None,
                        False
                        )
                self.assertEqual(ret, None)
                self.assertIn(1269190, self.bzapi.updates)
                self.assertIn('deadline', self.bzapi.updates[1269190])
                self.assertEqual(self.bzapi.updates[1269190]['deadline'],
                                 exp_deadline)
