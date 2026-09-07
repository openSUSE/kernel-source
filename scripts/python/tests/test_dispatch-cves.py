#!/usr/bin/python3
# -*- coding: utf-8 -*-

from xmlrpc.client import DateTime
from unittest import mock
import os
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
                  """
Security fix for CVE-2026-53035 bsc#1269190 with CVSS 7.0
ASSIGNEE: mkoutny@suse.com
CC: mkoutny@suse.com, mkoutny2@suse.com, mkoutny3@suse.com

NO ACTION NEEDED
""",
                  """
Security fix for CVE-2026-53035 bsc#1269190 with CVSS 7.0
ASSIGNEE: kernel-security-sentinel@lists.suse.com

NO ACTION NEEDED
""",
                  # all the branches that need an action are blacklisted
                  """
Security fix for CVE-2026-53035 bsc#1269190 with CVSS 5.5
SLE15-SP6-LTSS: MANUAL: backport 1234abcd (CVE-2026-53035 bsc#1269190)
SL-16.0: MANUAL: might need backport of 1234abcd (Fixes: v6.12)
    WW CONFIG_FOO not enabled.
BLACKLIST: SLE15-SP6-LTSS,SL-16.0
""",
                  """
Security fix for CVE-2026-53035 bsc#1269190 with CVSS 5.5
SLE15-SP6-LTSS: MANUAL: backport 1234abcd (CVE-2026-53035 bsc#1269190)
ASSIGNEE: mkoutny@suse.com
BLACKLIST: SLE15-SP6-LTSS
""",
                  """
Security fix for CVE-2026-53035 bsc#1269190 with CVSS 5.5
SLE15-SP6-LTSS: MANUAL: backport 1234abcd (CVE-2026-53035 bsc#1269190)
BLACKLIST: SLE15-SP6-LTSS and some junk
""",
                  # SL-16.0 needs an action but is not blacklisted, so the CVE is
                  # not decided and the ASSIGNEE has to take care of the rest
                  """
Security fix for CVE-2026-53035 bsc#1269190 with CVSS 5.5
SLE15-SP6-LTSS: MANUAL: backport 1234abcd (CVE-2026-53035 bsc#1269190)
SL-16.0: MANUAL: backport 1234abcd (Fixes: v6.12)
ASSIGNEE: mkoutny@suse.com
BLACKLIST: SLE15-SP6-LTSS
""",
                  # the wildcard stands for both the branches
                  """
Security fix for CVE-2026-53035 bsc#1269190 with CVSS 5.5
SLE15-SP6-LTSS: MANUAL: backport 1234abcd (CVE-2026-53035 bsc#1269190)
SL-16.0: MANUAL: might need backport of 1234abcd (Fixes: v6.12)
    WW CONFIG_FOO not enabled.
BLACKLIST: *
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
            'alias': ['CVE-2026-53035'],
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

    def test_single_dispatch_cc_more(self):
        ret = dispatch_cves.single_dispatch(
                self.bzapi,
                self.mockfiles[2].name,
                False,
                True, # yes
                True, # force
                None,
                False
                )
        self.assertEqual(ret, None)
        self.assertIn(1269190, self.bzapi.updates)
        self.assertEqual(self.bzapi.updates[1269190]['comment'],
                         'Security fix for CVE-2026-53035 bsc#1269190 with CVSS 7.0\n\nNO ACTION NEEDED\n')
        self.assertEqual(self.bzapi.updates[1269190]['assigned_to'],
                         'kernel-security-sentinel@lists.suse.com')
        self.assertIn('mkoutny@suse.com',  self.bzapi.updates[1269190]['cc_add'])
        self.assertIn('mkoutny2@suse.com', self.bzapi.updates[1269190]['cc_add'])
        self.assertIn('mkoutny3@suse.com', self.bzapi.updates[1269190]['cc_add'])
        self.assertNotIn('not.mkoutny@suse.com', self.bzapi.updates[1269190]['cc_add'])

    def test_single_dispatch_nonsuse_mail(self):
        ret = dispatch_cves.single_dispatch(
                self.bzapi,
                self.mockfiles[3].name,
                False,
                True, # yes
                True, # force
                None,
                False
                )
        self.assertEqual(ret, None)
        self.assertIn(1269190, self.bzapi.updates)
        self.assertEqual(self.bzapi.updates[1269190]['comment'],
                         'Security fix for CVE-2026-53035 bsc#1269190 with CVSS 7.0\n\nNO ACTION NEEDED\n')
        self.assertEqual(self.bzapi.updates[1269190]['assigned_to'],
                         'kernel-security-sentinel@lists.suse.com')

    def test_blacklist_cve_found(self):
        self.assertTrue(os.access(dispatch_cves.BLACKLIST_CVE, os.X_OK),
                        "{} is not executable".format(dispatch_cves.BLACKLIST_CVE))

    def test_single_dispatch_blacklist(self):
        self.bzapi.mockbugs[0].update({
            'assigned_to': 'kernel-bugs@suse.de',
        })

        with mock.patch.object(dispatch_cves.subprocess, 'run') as run:
            ret = dispatch_cves.single_dispatch(
                    self.bzapi,
                    self.mockfiles[4].name,
                    False,
                    True, # yes
                    False,
                    None,
                    False
                    )
        self.assertEqual(ret, None)
        self.assertIn(1269190, self.bzapi.updates)
        # the stanza itself is not a part of the comment, the request is
        self.assertEqual(self.bzapi.updates[1269190]['comment'],
                         'Security fix for CVE-2026-53035 bsc#1269190 with CVSS 5.5\n'
                         'SLE15-SP6-LTSS: MANUAL: backport 1234abcd (CVE-2026-53035 bsc#1269190)\n'
                         'SL-16.0: MANUAL: might need backport of 1234abcd (Fixes: v6.12)\n'
                         '    WW CONFIG_FOO not enabled.\n'
                         '\nRequesting to blacklist the CVE for: SLE15-SP6-LTSS,SL-16.0\n')
        # no ASSIGNEE given, blacklisting hands the bug back to the security team
        self.assertEqual(self.bzapi.updates[1269190]['assigned_to'],
                         'kernel-security-sentinel@lists.suse.com')
        # the mocked bug has no comments yet, so ours becomes #c0
        run.assert_called_once_with([dispatch_cves.BLACKLIST_CVE, 'add', 'CVE-2026-53035',
                                     'SLE15-SP6-LTSS,SL-16.0', 'https://bugzilla.suse.com/show_bug.cgi?id=1269190#c0'],
                                    check=True)

    def test_single_dispatch_blacklist_assignee(self):
        self.bzapi.mockbugs[0].update({
            'assigned_to': 'kernel-bugs@suse.de',
        })

        with mock.patch.object(dispatch_cves.subprocess, 'run') as run:
            ret = dispatch_cves.single_dispatch(
                    self.bzapi,
                    self.mockfiles[5].name,
                    False,
                    True, # yes
                    False,
                    None,
                    False
                    )
        self.assertEqual(ret, None)
        self.assertIn(1269190, self.bzapi.updates)
        # an explicit ASSIGNEE wins over the security team default
        self.assertEqual(self.bzapi.updates[1269190]['assigned_to'],
                         'mkoutny@suse.com')
        run.assert_called_once_with([dispatch_cves.BLACKLIST_CVE, 'add', 'CVE-2026-53035',
                                     'SLE15-SP6-LTSS', 'https://bugzilla.suse.com/show_bug.cgi?id=1269190#c0'],
                                    check=True)

    def test_single_dispatch_blacklist_partial(self):
        self.bzapi.mockbugs[0].update({
            'assigned_to': 'kernel-bugs@suse.de',
        })

        with mock.patch.object(dispatch_cves.subprocess, 'run') as run:
            ret = dispatch_cves.single_dispatch(
                    self.bzapi,
                    self.mockfiles[7].name,
                    False,
                    True, # yes
                    False,
                    None,
                    False
                    )
        self.assertEqual(ret, None)
        self.assertIn(1269190, self.bzapi.updates)
        # SL-16.0 still needs an action, hence no handover to the security team
        self.assertEqual(self.bzapi.updates[1269190]['assigned_to'],
                         'mkoutny@suse.com')
        # the partial request is submitted nevertheless
        run.assert_called_once_with([dispatch_cves.BLACKLIST_CVE, 'add', 'CVE-2026-53035',
                                     'SLE15-SP6-LTSS', 'https://bugzilla.suse.com/show_bug.cgi?id=1269190#c0'],
                                    check=True)

    def test_single_dispatch_blacklist_wildcard(self):
        self.bzapi.mockbugs[0].update({
            'assigned_to': 'kernel-bugs@suse.de',
        })

        with mock.patch.object(dispatch_cves.subprocess, 'run') as run:
            ret = dispatch_cves.single_dispatch(
                    self.bzapi,
                    self.mockfiles[8].name,
                    False,
                    True, # yes
                    False,
                    None,
                    False
                    )
        self.assertEqual(ret, None)
        self.assertIn(1269190, self.bzapi.updates)
        # '*' covers all the branches that need an action, so the bug is decided
        self.assertEqual(self.bzapi.updates[1269190]['assigned_to'],
                         'kernel-security-sentinel@lists.suse.com')
        # ...and it is expanded to those branches for the request
        run.assert_called_once_with([dispatch_cves.BLACKLIST_CVE, 'add', 'CVE-2026-53035',
                                     'SLE15-SP6-LTSS,SL-16.0', 'https://bugzilla.suse.com/show_bug.cgi?id=1269190#c0'],
                                    check=True)

    def test_single_dispatch_blacklist_bugzilla_failed(self):
        self.bzapi.mockbugs[0].update({
            'assigned_to': 'kernel-bugs@suse.de',
        })

        with mock.patch.object(dispatch_cves.subprocess, 'run') as run:
            with mock.patch.object(self.bzapi, 'update_bugs', side_effect=Exception('nope')):
                ret = dispatch_cves.single_dispatch(
                        self.bzapi,
                        self.mockfiles[4].name,
                        False,
                        True, # yes
                        False,
                        None,
                        False
                        )
        self.assertEqual(ret, None)
        # there is no comment to refer to when the bugzilla update failed
        run.assert_not_called()

    def test_single_dispatch_blacklist_junk(self):
        self.bzapi.mockbugs[0].update({
            'assigned_to': 'kernel-bugs@suse.de',
        })

        with mock.patch.object(dispatch_cves.subprocess, 'run') as run:
            ret = dispatch_cves.single_dispatch(
                    self.bzapi,
                    self.mockfiles[6].name,
                    False,
                    True, # yes
                    False,
                    None,
                    False
                    )
        self.assertEqual(ret, None)
        self.assertIn(1269190, self.bzapi.updates)
        run.assert_called_once_with([dispatch_cves.BLACKLIST_CVE, 'add', 'CVE-2026-53035',
                                     'SLE15-SP6-LTSS', 'https://bugzilla.suse.com/show_bug.cgi?id=1269190#c0'],
                                    check=True)
