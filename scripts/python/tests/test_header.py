#!/usr/bin/env python
# -*- coding: utf-8 -*-,
# vim:set shiftwidth=4 softtabstop=4 expandtab textwidth=79:

import sys
import os.path
import unittest
from StringIO import StringIO

from suse_git import header

# You'll see a slightly strange pattern here:
#   try:
#       self.sometest()
#       self.assertTrue(False)
#   except Exception, e:
#       rest of test
#
# This is to test the exception contents.  Python's unittest module
# allows us to assert that a particular exception is raised but
# it won't let us inspect the contents of it.  The assertTrue(False)
# will cause a test failure if an exception isn't raised; The
# except HeaderException clause will cause a test failure if the
# exception isn't HeaderException.  When adding new test cases,
# please follow this pattern when the test case is expecting to fail.

class TestHeaderChecker(unittest.TestCase):
    def setUp(self):
        self.header = header.Checker()

    def test_empty(self):
        try:
            self.header.do_patch("")
        except header.HeaderException, e:
            self.assertTrue(e.errors(header.MissingTagError) == 1)
            self.assertTrue(e.tag_is_missing('patch-mainline'))
            self.assertTrue(e.errors() == 1)

    def test_patch_mainline_dupe(self):
        text = """
Patch-mainline: v4.2-rc1
Patch-mainline: v4.2-rc2
Git-commit: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
Acked-by: developer@suse.com
"""
        try:
            self.header.do_patch(text)
            self.assertTrue(False)
        except header.HeaderException, e:
            self.assertTrue(e.errors(header.DuplicateTagError) == 1)
            self.assertTrue(e.errors() == 1)

    def test_patch_mainline_empty(self):
        text = """
Patch-mainline:
Acked-by: developer@suse.com
"""
        try:
            self.header.do_patch(text)
            self.assertTrue(False)
        except header.HeaderException, e:
            self.assertTrue(e.errors(header.EmptyTagError) == 1)
            self.assertTrue(e.errors(header.MissingTagError) == 1)
            self.assertTrue(e.tag_is_missing('patch-mainline'))
            self.assertTrue(e.errors() == 2)

    def test_patch_mainline_version_no_ack_or_sob(self):
        text = """
Patch-mainline: v4.2-rc1
Git-commit: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
"""

        try:
            self.header.do_patch(text)
        except header.HeaderException, e:
            self.assertTrue(e.errors(header.MissingTagError) == 1)
            self.assertTrue(e.tag_is_missing('acked-by'))
            self.assertTrue(e.tag_is_missing('signed-off-by'))
            self.assertTrue(e.errors() == 1)

    def test_patch_mainline_version_correct_multi_ack(self):
        text = """
Patch-mainline: v4.2-rc1
Git-commit: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
Acked-by: developer@external.com
Acked-by: developer@suse.com
"""
        self.header.do_patch(text)

    def test_patch_mainline_version_correct_multi_ack_ext_last(self):
        text = """
Patch-mainline: v4.2-rc1
Git-commit: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
Acked-by: developer@suse.com
Acked-by: developer@external.com
"""
        self.header.do_patch(text)

    def test_patch_mainline_version_correct_mixed_ack_sob(self):
        text = """
Patch-mainline: v4.2-rc1
Git-commit: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
Signed-off-by: developer@external.com
Acked-by: developer@suse.com
"""
        self.header.do_patch(text)

    def test_patch_mainline_version_correct_ack(self):
        text = """
Patch-mainline: v4.2-rc1
Git-commit: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
Acked-by: developer@suse.com
"""
        self.header.do_patch(text)

    def test_patch_mainline_version_correct_from(self):
        text = """
From: developer@suse.com
Patch-mainline: v4.2-rc1
Git-commit: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
"""
        self.header.do_patch(text)

    def test_patch_mainline_version_correct_review(self):
        text = """
From: developer@external.com
Patch-mainline: v4.2-rc1
Git-commit: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa

Reviewed-by: developer@suse.com
"""
        self.header.do_patch(text)

    def test_patch_mainline_version_correct_sob(self):
        text = """
Patch-mainline: v4.2-rc1
Git-commit: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
Signed-off-by: developer@suse.com
"""
        self.header.do_patch(text)

    def test_patch_mainline_version_correct_multi_sob(self):
        text = """
Patch-mainline: v4.2-rc1
Git-commit: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
Signed-off-by: developer2@external.com
Signed-off-by: developer@suse.com
"""
        self.header.do_patch(text)

    def test_patch_mainline_version_correct_multi_sob_ext_last(self):
        text = """
Patch-mainline: v4.2-rc1
Git-commit: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
Signed-off-by: developer@suse.com
Signed-off-by: developer2@external.com
"""
        self.header.do_patch(text)

    def test_patch_mainline_na(self):
        text = """
Patch-mainline: n/a
Acked-by: developer@suse.com
"""
        try:
            self.header.do_patch(text)
            self.assertTrue(False)
        except header.HeaderException, e:
            self.assertTrue(e.errors(header.FormatError) == 1)
            self.assertTrue(e.errors() == 1)

    def test_patch_mainline_submitted_correct_ml(self):
        text = """
Patch-mainline: Submitted, 19 July 2015 - linux-btrfs
Acked-by: developer@suse.com
"""
        errors = self.header.do_patch(text)

    def test_patch_mainline_submitted_correct_url(self):
        text = """
Patch-mainline: Submitted, https://lkml.org/archive/link-to-post
Acked-by: developer@suse.com
"""
        errors = self.header.do_patch(text)

    def test_patch_mainline_submitted_no_detail(self):
        text = """
Patch-mainline: Submitted
Acked-by: developer@suse.com
"""
        try:
            self.header.do_patch(text)
            self.assertTrue(False)
        except header.HeaderException, e:
            self.assertTrue(e.errors(header.FormatError) == 1)
            self.assertTrue(e.errors() == 1)

    def test_patch_mainline_submitted_detail_git_commit(self):
        text = """
Patch-mainline: Submitted, https://lkml.org/archive/link-to-post
Git-repo: git://host/valid/path/to/repo
Acked-by: developer@suse.com
"""
        try:
            self.header.do_patch(text)
            self.assertTrue(False)
        except header.HeaderException, e:
            self.assertTrue(e.errors(header.ExcludedTagError) == 1)
            self.assertTrue(e.errors() == 1)

    # Required/Excluded conflict between Patch-mainline (Submitted)
    # and Git-commit
    def test_patch_mainline_submitted_detail_git_commit(self):
        text = """
Patch-mainline: Submitted, https://lkml.org/archive/link-to-post
Git-commit: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
Acked-by: developer@suse.com
"""
        try:
            self.header.do_patch(text)
            self.assertTrue(False)
        except header.HeaderException, e:
            self.assertTrue(e.errors(header.MissingTagError) == 1)
            self.assertTrue(e.errors(header.ExcludedTagError) == 1)
            self.assertTrue(e.errors() == 2)

    def test_patch_mainline_submitted_no_detail(self):
        text = """
Patch-mainline: Submitted
Acked-by: developer@suse.com
"""
        try:
            self.header.do_patch(text)
            self.assertTrue(False)
        except header.HeaderException, e:
            self.assertTrue(e.errors(header.FormatError) == 1)
            self.assertTrue(e.errors() == 1)

    def test_patch_mainline_never_no_detail(self):
        text = """
Patch-mainline: Never
Acked-by: developer@suse.com
"""
        try:
            self.header.do_patch(text)
        except header.HeaderException, e:
            self.assertTrue(e.errors(header.FormatError) == 1)
            self.assertTrue(e.errors() == 1)

    def test_patch_mainline_yes_with_detail(self):
        text = """
Patch-mainline: Yes, v4.1-rc1
Acked-by: developer@suse.com
"""
        try:
            self.header.do_patch(text)
            self.assertTrue(False)
        except header.HeaderException, e:
            self.assertTrue(e.errors(header.FormatError) == 1)
            self.assertTrue(e.errors() == 1)

    def test_patch_mainline_yes_no_detail(self):
        text = """
Patch-mainline: Yes
Acked-by: developer@suse.com
"""
        try:
            self.header.do_patch(text)
            self.assertTrue(False)
        except header.HeaderException, e:
            self.assertTrue(e.errors(header.FormatError) == 1)
            self.assertTrue(e.errors() == 1)

    def test_patch_mainline_not_yet_no_detail(self):
        text = """
Patch-mainline: Not yet
Acked-by: developer@suse.com
"""
        try:
            self.header.do_patch(text)
            self.assertTrue(False)
        except header.HeaderException, e:
            self.assertTrue(e.errors(header.FormatError) == 1)
            self.assertTrue(e.errors() == 1)

    def test_patch_mainline_never_detail(self):
        text = """
Patch-mainline: Never, SLES-specific feature
Acked-by: developer@suse.com
"""
        self.header.do_patch(text)

    def test_patch_mainline_no_detail(self):
        text = """
Patch-mainline: No, handled differently upstream
Acked-by: developer@suse.com
"""
        self.header.do_patch(text)

    def test_patch_mainline_not_yet_detail(self):
        text = """
Patch-mainline: Not yet, rare reason
Acked-by: developer@suse.com
"""
        self.header.do_patch(text)

    def test_git_commit_standalone(self):
        text = """
Git-commit: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
Acked-by: developer@suse.com
"""
        try:
            self.header.do_patch(text)
        except header.HeaderException, e:
            # Both policy and Git-commit require Patch-mainline
            self.assertTrue(e.errors(header.MissingTagError) == 2)
            self.assertTrue(e.tag_is_missing('patch-mainline'))
            self.assertTrue(e.errors() == 2)

    def test_patch_mainline_queued_correct(self):
        text = """
Patch-mainline: Queued
Git-repo: git://path/to/git/repo
Git-commit: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
Acked-by: developer@suse.com
"""
        self.header.do_patch(text)

    def test_patch_mainline_queued_standalone(self):
        text = """
Patch-mainline: Queued
Acked-by: developer@suse.com
"""
        try:
            self.header.do_patch(text)
            self.assertTrue(False)
        except header.HeaderException, e:
            self.assertTrue(e.errors(header.MissingTagError) == 2)
            self.assertTrue(e.tag_is_missing('git-commit'))
            self.assertTrue(e.tag_is_missing('git-repo'))
            self.assertTrue(e.errors() == 2)

    def test_patch_mainline_queued_with_git_repo(self):
        text = """
Patch-mainline: Queued
Git-repo: git://path/to/git/repo
Acked-by: developer@suse.com
"""
        try:
            self.header.do_patch(text)
            self.assertTrue(False)
        except header.HeaderException, e:
            # Required by both Patch-mainline (Queued) and
            # Git-repo
            self.assertTrue(e.errors(header.MissingTagError) == 2)
            self.assertTrue(e.tag_is_missing('git-commit'))
            self.assertTrue(e.errors() == 2)

    def test_patch_mainline_queued_with_git_commit(self):
        text = """
Patch-mainline: Queued
Git-commit: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
Acked-by: developer@suse.com
"""
        try:
            self.header.do_patch(text)
            self.assertTrue(False)
        except header.HeaderException, e:
            self.assertTrue(e.errors(header.MissingTagError) == 1)
            self.assertTrue(e.tag_is_missing('git-repo'))
            self.assertTrue(e.errors() == 1)

    def test_patch_mainline_invalid(self):
        text = """
Patch-mainline: n/a
Acked-by: developer@suse.com
"""
        try:
            self.header.do_patch(text)
            self.assertTrue(False)
        except header.HeaderException, e:
            self.assertTrue(e.errors(header.FormatError) == 1)
            self.assertTrue(e.errors() == 1)

    def test_diff_like_description(self):
        text = """
From: developer@external.com
Subject: blablah
Patch-mainline: v4.2-rc1
Git-commit: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa

This is a thing. I ran across it:
*** Testing resulted in failure

Acked-by: developer@suse.com
"""
        self.header.do_patch(text)

    def test_diff_like_description2(self):
        text = """
From: developer@external.com
Subject: blablah
Patch-mainline: v4.2-rc1
Git-commit: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa

This is a thing. I ran across it:
--- Testing resulted in failure

Acked-by: developer@suse.com
"""
        self.header.do_patch(text)
