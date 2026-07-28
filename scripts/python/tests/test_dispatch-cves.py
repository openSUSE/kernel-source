#!/usr/bin/python3
# -*- coding: utf-8 -*-

from datetime import datetime
import tempfile
import unittest

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


class TestDispatchCves(unittest.TestCase):
    def setUp(self):
        self.bzapi = BZMock()
        self.file = tempfile.NamedTemporaryFile('w', encoding='utf-8')
        self.file.write("""
Security fix for CVE-2026-53035 bsc#1269190 with CVSS 5.5
ASSIGNEE: mkoutny@suse.com
CC: mkoutny@suse.com

NO ACTION NEEDED
""".lstrip())
        self.file.flush()

        self.bzapi.mockbugs.append(DictObj({
            'id': 1269190,
            'alias': 'CVE-2026-53035',
            'assigned_to': 'not.mkoutny@suse.com',
            'cc': [],
            'flags': [],
            'product': 'SUSE Security Incidents',
            }))


    def tearDown(self):
        self.file.close()


    def test_single_dispatch(self):
        self.bzapi.mockbugs[0].update({
            'assigned_to': 'kernel-bugs@suse.de',
        })

        ret = dispatch_cves.single_dispatch(
                self.bzapi,
                self.file.name,
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
