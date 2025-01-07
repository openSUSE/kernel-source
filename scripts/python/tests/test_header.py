#!/usr/bin/env python3
# -*- coding: utf-8 -*-,
# vim:set shiftwidth=4 softtabstop=4 expandtab textwidth=79:

import sys
import os.path
import unittest

from suse_git import header

class TestHeaderChecker(unittest.TestCase):
    def test_empty(self):
        try:
            self.header = header.Checker("")
        except header.HeaderException as e:
            self.assertEqual(4, e.errors(header.MissingTagError))
            self.assertTrue(e.tag_is_missing('patch-mainline'))
            self.assertTrue(e.tag_is_missing('from'))
            self.assertTrue(e.tag_is_missing('subject'))
            self.assertTrue(e.tag_is_missing('references'))
            self.assertEqual(4, e.errors())

    def test_subject_dupe(self):
        text = """
From: develoepr@site.com
Subject: some patch
Subject: some patch
Patch-mainline: v4.2-rc2
Git-commit: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
References: bsc#12345
Acked-by: developer@suse.com
"""
        with self.assertRaises(header.HeaderException) as cm:
            self.header = header.Checker(text)
        e = cm.exception
        self.assertEqual(1, e.errors(header.DuplicateTagError))
        self.assertEqual(1, e.errors())

    def test_patch_mainline_dupe(self):
        text = """
From: developer@site.com
Subject: some patch
Patch-mainline: v4.2-rc1
Patch-mainline: v4.2-rc2
Git-commit: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
References: bsc#12345
Acked-by: developer@suse.com
"""
        with self.assertRaises(header.HeaderException) as cm:
            self.header = header.Checker(text)

        e = cm.exception
        self.assertEqual(1, e.errors(header.DuplicateTagError))
        self.assertEqual(1, e.errors())

    def test_patch_mainline_empty(self):
        text = """
From: developer@site.com
Subject: some patch
Patch-mainline:
References: bsc#12345
Acked-by: developer@suse.com
"""
        with self.assertRaises(header.HeaderException) as cm:
            self.header = header.Checker(text)

        e = cm.exception
        self.assertEqual(1, e.errors(header.EmptyTagError))
        self.assertEqual(1, e.errors(header.MissingTagError))
        self.assertTrue(e.tag_is_missing('patch-mainline'))
        self.assertEqual(2, e.errors())

    def test_patch_mainline_version_no_ack_or_sob(self):
        text = """
From: developer@site.com
Subject: some patch
Patch-mainline: v4.2-rc1
References: bsc#12345
Git-commit: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
"""

        try:
            self.header = header.Checker(text)
        except header.HeaderException as e:
            self.assertEqual(1, e.errors(header.MissingTagError))
            self.assertTrue(e.tag_is_missing('acked-by'))
            self.assertTrue(e.tag_is_missing('signed-off-by'))
            self.assertEqual(1, e.errors())

    def test_patch_mainline_version_correct_multi_ack(self):
        text = """
From: developer@site.com
Subject: some patch
Patch-mainline: v4.2-rc1
Git-commit: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
References: bsc#12345
Acked-by: developer@external.com
Acked-by: developer@suse.com
"""
        self.header = header.Checker(text)

    def test_patch_mainline_version_correct_multi_ack_ext_last(self):
        text = """
From: developer@site.com
Subject: some patch
Patch-mainline: v4.2-rc1
Git-commit: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
References: bsc#12345
Acked-by: developer@suse.com
Acked-by: developer@external.com
"""
        self.header = header.Checker(text)

    def test_patch_mainline_version_correct_mixed_ack_sob(self):
        text = """
From: developer@site.com
Subject: some patch
Patch-mainline: v4.2-rc1
Git-commit: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
References: bsc#12345
Signed-off-by: developer@external.com
Acked-by: developer@suse.com
"""
        self.header = header.Checker(text)

    def test_patch_mainline_version_correct_ack(self):
        text = """
From: developer@site.com
Subject: some patch
Patch-mainline: v4.2-rc1
Git-commit: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
References: bsc#12345
Acked-by: developer@suse.com
"""
        self.header = header.Checker(text)

    def test_patch_mainline_version_correct_from(self):
        text = """
From: developer@suse.com
Subject: some patch
Patch-mainline: v4.2-rc1
Git-commit: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
References: bsc#12345
"""
        self.header = header.Checker(text)

    def test_patch_mainline_version_correct_review(self):
        text = """
From: developer@external.com
Subject: some patch
Patch-mainline: v4.2-rc1
Git-commit: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
References: bsc#12345

Reviewed-by: developer@suse.com
"""
        self.header = header.Checker(text)

    def test_patch_mainline_version_correct_sob(self):
        text = """
From: developer@site.com
Subject: some patch
Patch-mainline: v4.2-rc1
Git-commit: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
References: bsc#12345
Signed-off-by: developer@suse.com
"""
        self.header = header.Checker(text)

    def test_patch_mainline_version_correct_multi_sob(self):
        text = """
From: developer@site.com
Subject: some patch
Patch-mainline: v4.2-rc1
Git-commit: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
References: bsc#12345
Signed-off-by: developer2@external.com
Signed-off-by: developer@suse.com
"""
        self.header = header.Checker(text)

    def test_patch_mainline_version_correct_multi_sob_ext_last(self):
        text = """
From: developer@site.com
Subject: some patch
Patch-mainline: v4.2-rc1
Git-commit: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
References: bsc#12345
Signed-off-by: developer@suse.com
Signed-off-by: developer2@external.com
"""
        self.header = header.Checker(text)

    def test_patch_mainline_na(self):
        text = """
From: developer@site.com
Subject: some patch
Patch-mainline: n/a
References: bsc#12345
Acked-by: developer@suse.com
"""
        with self.assertRaises(header.HeaderException) as cm:
            self.header = header.Checker(text)

        e = cm.exception
        self.assertEqual(1, e.errors(header.FormatError))
        self.assertEqual(1, e.errors())

    def test_patch_mainline_submitted_correct_ml(self):
        text = """
From: developer@site.com
Subject: some patch
Patch-mainline: Submitted, 19 July 2015 - linux-btrfs
References: bsc#12345
Acked-by: developer@suse.com
"""
        errors = self.header = header.Checker(text)

    def test_patch_mainline_submitted_correct_url(self):
        text = """
From: developer@site.com
Subject: some patch
Patch-mainline: Submitted, https://lkml.org/archive/link-to-post
References: bsc#12345
Acked-by: developer@suse.com
"""
        errors = self.header = header.Checker(text)

    def test_patch_mainline_submitted_no_detail(self):
        text = """
From: developer@site.com
Subject: some patch
Patch-mainline: Submitted
References: bsc#12345
Acked-by: developer@suse.com
"""
        with self.assertRaises(header.HeaderException) as cm:
            self.header = header.Checker(text)

        e = cm.exception
        self.assertEqual(1, e.errors(header.FormatError))
        self.assertEqual(1, e.errors())

    def test_patch_mainline_submitted_detail_git_commit(self):
        text = """
From: developer@site.com
Subject: some patch
Patch-mainline: Submitted, https://lkml.org/archive/link-to-post
Git-repo: git://host/valid/path/to/repo
References: bsc#12345
Acked-by: developer@suse.com
"""
        with self.assertRaises(header.HeaderException) as cm:
            self.header = header.Checker(text)

        e = cm.exception
        self.assertEqual(1, e.errors(header.ExcludedTagError))
        self.assertEqual(1, e.errors())

    # Required/Excluded conflict between Patch-mainline (Submitted)
    # and Git-commit
    def test_patch_mainline_submitted_detail_git_commit(self):
        text = """
From: developer@site.com
Subject: some patch
Patch-mainline: Submitted, https://lkml.org/archive/link-to-post
Git-commit: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
References: bsc#12345
Acked-by: developer@suse.com
"""
        with self.assertRaises(header.HeaderException) as cm:
            self.header = header.Checker(text)

        e = cm.exception
        self.assertEqual(1, e.errors(header.MissingTagError))
        self.assertEqual(1, e.errors(header.ExcludedTagError))
        self.assertEqual(2, e.errors())

    def test_patch_mainline_submitted_no_detail(self):
        text = """
From: developer@site.com
Subject: some patch
Patch-mainline: Submitted
References: bsc#12345
Acked-by: developer@suse.com
"""
        with self.assertRaises(header.HeaderException) as cm:
            self.header = header.Checker(text)

        e = cm.exception
        self.assertEqual(1, e.errors(header.FormatError))
        self.assertEqual(1, e.errors())

    def test_patch_mainline_never_no_detail(self):
        text = """
From: developer@site.com
Subject: some patch
Patch-mainline: Never
References: bsc#12345
Acked-by: developer@suse.com
"""
        try:
            self.header = header.Checker(text)
        except header.HeaderException as e:
            self.assertEqual(1, e.errors(header.FormatError))
            self.assertEqual(1, e.errors())

    def test_patch_mainline_yes_with_detail(self):
        text = """
From: developer@site.com
Subject: some patch
Patch-mainline: Yes, v4.1-rc1
References: bsc#12345
Acked-by: developer@suse.com
"""
        with self.assertRaises(header.HeaderException) as cm:
            self.header = header.Checker(text)

        e = cm.exception
        self.assertEqual(1, e.errors(header.FormatError))
        self.assertEqual(1, e.errors())

    def test_patch_mainline_yes_no_detail(self):
        text = """
From: developer@site.com
Subject: some patch
Patch-mainline: Yes
References: bsc#12345
Acked-by: developer@suse.com
"""
        with self.assertRaises(header.HeaderException) as cm:
            self.header = header.Checker(text)

        e = cm.exception
        self.assertEqual(1, e.errors(header.FormatError))
        self.assertEqual(1, e.errors())

    def test_patch_mainline_not_yet_no_detail(self):
        text = """
From: developer@site.com
Subject: some patch
Patch-mainline: Not yet
References: bsc#12345
Acked-by: developer@suse.com
"""
        with self.assertRaises(header.HeaderException) as cm:
            self.header = header.Checker(text)

        e = cm.exception
        self.assertEqual(1, e.errors(header.FormatError))
        self.assertEqual(1, e.errors())

    def test_patch_mainline_never_detail(self):
        text = """
From: developer@site.com
Subject: some patch
Patch-mainline: Never, SLES-specific feature
References: FATE#123456
Acked-by: developer@suse.com
"""
        self.header = header.Checker(text)

    def test_patch_mainline_no_detail(self):
        text = """
From: developer@site.com
Subject: some patch
Patch-mainline: No, handled differently upstream
References: bsc#12345
Acked-by: developer@suse.com
"""
        with self.assertRaises(header.HeaderException) as cm:
            self.header = header.Checker(text)

        e = cm.exception
        self.assertEqual(1, e.errors(header.FormatError))
        self.assertEqual(1, e.errors())

    def test_patch_mainline_not_yet_detail(self):
        text = """
From: developer@site.com
Subject: some patch
Patch-mainline: Not yet, rare reason
References: bsc#12345
Acked-by: developer@suse.com
"""
        self.header = header.Checker(text)

    def test_git_commit_standalone(self):
        text = """
From: developer@site.com
Subject: some patch
Git-commit: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
References: bsc#12345
Acked-by: developer@suse.com
"""
        try:
            self.header = header.Checker(text)
        except header.HeaderException as e:
            # Both policy and Git-commit require Patch-mainline
            self.assertEqual(2, e.errors(header.MissingTagError))
            self.assertTrue(e.tag_is_missing('patch-mainline'))
            self.assertEqual(2, e.errors())

    def test_alt_commit_short(self):
        text = """
From: developer@site.com
Subject: some patch
Patch-mainline: v4.2-rc2
Git-commit: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
Alt-commit: bbbbbbbbbb
References: bsc#12345
Acked-by: developer@suse.com
"""

        try:
            self.header = header.Checker(text)
        except header.HeaderException as e:
            self.assertEqual(1, e.errors(header.FormatError))
            self.assertEqual(1, e.errors())

    def test_alt_commit_many(self):
        text = """
From: developer@site.com
Subject: some patch
Patch-mainline: v4.2-rc2
Git-commit: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
Alt-commit: bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb cccccccccccccccccccccccccccccccccccccccc
References: bsc#12345
Acked-by: developer@suse.com
"""

        try:
            self.header = header.Checker(text)
        except header.HeaderException as e:
            self.assertEqual(1, e.errors(header.FormatError))
            self.assertEqual(1, e.errors())

    def test_alt_commit_correct(self):
        text = """
From: developer@site.com
Subject: some patch
Patch-mainline: v4.2-rc2
Git-commit: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
Alt-commit: bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
References: bsc#12345
Acked-by: developer@suse.com
"""
        self.header = header.Checker(text)

    def test_alt_commit_multi_correct(self):
        text = """
From: developer@site.com
Subject: some patch
Patch-mainline: v4.2-rc2
Git-commit: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
Alt-commit: bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
Alt-commit: cccccccccccccccccccccccccccccccccccccccc
References: bsc#12345
Acked-by: developer@suse.com
"""
        self.header = header.Checker(text)

    def test_patch_mainline_queued_correct(self):
        text = """
From: developer@site.com
Subject: some patch
Patch-mainline: Queued
Git-repo: git://path/to/git/repo
Git-commit: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
References: bsc#12345
Acked-by: developer@suse.com
"""
        self.header = header.Checker(text)

    def test_patch_mainline_queued_standalone(self):
        text = """
From: developer@site.com
Subject: some patch
Patch-mainline: Queued
References: bsc#12345
Acked-by: developer@suse.com
"""
        with self.assertRaises(header.HeaderException) as cm:
            self.header = header.Checker(text)

        e = cm.exception
        self.assertEqual(2, e.errors(header.MissingTagError))
        self.assertTrue(e.tag_is_missing('git-commit'))
        self.assertTrue(e.tag_is_missing('git-repo'))
        self.assertEqual(2, e.errors())

    def test_patch_mainline_queued_with_git_repo(self):
        text = """
From: developer@site.com
Subject: some patch
Patch-mainline: Queued
Git-repo: git://path/to/git/repo
References: bsc#12345
Acked-by: developer@suse.com
"""
        with self.assertRaises(header.HeaderException) as cm:
            self.header = header.Checker(text)

        e = cm.exception
        # Required by both Patch-mainline (Queued) and
        # Git-repo
        self.assertEqual(2, e.errors(header.MissingTagError))
        self.assertTrue(e.tag_is_missing('git-commit'))
        self.assertEqual(2, e.errors())

    def test_patch_mainline_queued_with_git_commit(self):
        text = """
From: developer@site.com
Subject: some patch
Patch-mainline: Queued
Git-commit: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
References: bsc#12345
Acked-by: developer@suse.com
"""
        with self.assertRaises(header.HeaderException) as cm:
            self.header = header.Checker(text)

        e = cm.exception
        self.assertEqual(1, e.errors(header.MissingTagError))
        self.assertTrue(e.tag_is_missing('git-repo'))
        self.assertEqual(1, e.errors())

    def test_patch_mainline_invalid(self):
        text = """
From: developer@site.com
Subject: some patch
Patch-mainline: n/a
References: bsc#12345
Acked-by: developer@suse.com
"""
        with self.assertRaises(header.HeaderException) as cm:
            self.header = header.Checker(text)

        e = cm.exception
        self.assertEqual(1, e.errors(header.FormatError))
        self.assertEqual(1, e.errors())

    def test_diff_like_description(self):
        text = """
From: developer@external.com
Subject: blablah
Patch-mainline: v4.2-rc1
Git-commit: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
References: bsc#12345

This is a thing. I ran across it:
*** Testing resulted in failure

Acked-by: developer@suse.com
"""
        self.header = header.Checker(text)

    def test_diff_like_description2(self):
        text = """
From: developer@external.com
Subject: blablah
Patch-mainline: v4.2-rc1
Git-commit: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
References: bsc#12345

This is a thing. I ran across it:
--- Testing resulted in failure

Acked-by: developer@suse.com
"""
        self.header = header.Checker(text)

    def test_patch_references_empty(self):
        text = """
From: developer@site.com
Subject: some patch
Patch-mainline: v4.2-rc1
Git-commit: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
References:
Acked-by: developer@suse.com
"""
        with self.assertRaises(header.HeaderException) as cm:
            self.header = header.Checker(text)

        e = cm.exception
        self.assertEqual(1, e.errors(header.EmptyTagError))
        self.assertEqual(1, e.errors(header.MissingTagError))
        self.assertTrue(e.tag_is_missing('references'))
        self.assertEqual(2, e.errors())

    def test_patch_references_missing(self):
        text = """
From: developer@site.com
Subject: some patch
Patch-mainline: v4.2-rc1
Git-commit: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
Acked-by: developer@suse.com
"""
        with self.assertRaises(header.HeaderException) as cm:
            self.header = header.Checker(text)

        e = cm.exception
        self.assertEqual(1, e.errors(header.MissingTagError))
        self.assertTrue(e.tag_is_missing('references'))
        self.assertEqual(1, e.errors())

    def test_patch_references_multi(self):
        text = """
From: developer@site.com
Subject: some patch
Patch-mainline: v4.2-rc1
Git-commit: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
References: bsc#12345
References: bsc#12354
Acked-by: developer@suse.com
"""
        self.header = header.Checker(text)

    def test_patch_references_multi2(self):
        text = """
From: developer@site.com
Subject: some patch
Patch-mainline: v4.2-rc1
Git-commit: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
References: bsc#12345 bsc#12354
Acked-by: developer@suse.com
"""
        self.header = header.Checker(text)

    def test_patch_references_multi3(self):
        text = """
From: developer@site.com
Subject: some patch
Patch-mainline: v4.2-rc1
Git-commit: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
References: bsc#12345, bsc#12354
Acked-by: developer@suse.com
"""
        self.header = header.Checker(text)


    def test_patch_references_multi3(self):
        text = """
From: developer@site.com
Subject: some patch
Patch-mainline: v4.2-rc1
Git-commit: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
References: bsc#12345, bsc#12354
References: fix for blahblah
Acked-by: developer@suse.com
"""
        self.header = header.Checker(text)



    @unittest.skip("Enable this check when we want to require a real "
                   "References tag")
    def test_patch_references_only_freeform(self):
        text = """
From: developer@site.com
Subject: some patch
Patch-mainline: v4.2-rc1
Git-commit: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
References: fix for blahblah
Acked-by: developer@suse.com
"""
        with self.assertRaises(header.HeaderException) as cm:
            self.header = header.Checker(text)

        e = cm.exception
        self.assertEqual(1, e.errors(header.MissingTagError))
        self.assertTrue(e.tag_is_missing('references'))
        self.assertEqual(1, e.errors())


    def test_patch_references_empty_update(self):
        text = """
From: developer@site.com
Subject: some patch
Patch-mainline: v4.2-rc1
Git-commit: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
References:
Acked-by: developer@suse.com
"""
        with self.assertRaises(header.HeaderException) as cm:
            self.header = header.Checker(text, True)

        e = cm.exception
        self.assertEqual(1, e.errors(header.EmptyTagError))
        self.assertEqual(1, e.errors())

    def test_patch_references_missing_update(self):
        text = """
From: developer@site.com
Subject: some patch
Patch-mainline: v4.2-rc1
Git-commit: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
Acked-by: developer@suse.com
"""
        self.header = header.Checker(text, True)

    def test_patch_references_multi_update(self):
        text = """
From: developer@site.com
Subject: some patch
Patch-mainline: v4.2-rc1
Git-commit: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
References: bsc#12345
References: bsc#12354
Acked-by: developer@suse.com
"""
        self.header = header.Checker(text, True)

    def test_patch_references_multi2_update(self):
        text = """
From: developer@site.com
Subject: some patch
Patch-mainline: v4.2-rc1
Git-commit: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
References: bsc#12345 bsc#12354
Acked-by: developer@suse.com
"""
        self.header = header.Checker(text, True)

    def test_patch_references_multi3_update(self):
        text = """
From: developer@site.com
Subject: some patch
Patch-mainline: v4.2-rc1
Git-commit: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
References: bsc#12345, bsc#12354
Acked-by: developer@suse.com
"""
        self.header = header.Checker(text, True)


    def test_patch_references_multi3_update(self):
        text = """
From: developer@site.com
Subject: some patch
Patch-mainline: v4.2-rc1
Git-commit: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
References: bsc#12345, bsc#12354
References: fix for blahblah
Acked-by: developer@suse.com
"""
        self.header = header.Checker(text, True)


    @unittest.skip("Enable this check when we want to require a real "
                   "References tag")
    def test_patch_references_only_freeform_update(self):
        text = """
From: developer@site.com
Subject: some patch
Patch-mainline: v4.2-rc1
Git-commit: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
References: fix for blahblah
Acked-by: developer@suse.com
"""
        with self.assertRaises(header.HeaderException) as cm:
            self.header = header.Checker(text, True)

        e = cm.exception
        self.assertEqual(1, e.errors(header.MissingTagError))
        self.assertTrue(e.tag_is_missing('references'))
        self.assertEqual(1, e.errors())

    def test_no_patch_mainline_for_kabi(self):
        text = """
From: developer@site.com
Subject: some patch
References: FATE#123456
Acked-by: developer@suse.com
"""
        self.header = header.Checker(text, False, "patches.kabi/FATE123456_fix_kabi.patch")

    def test_patch_mainline_invalid2(self):
        text = """
From: developer@site.com
Subject: some patch
Patch-mainline: Not yet, submitted 2022-08-23
References: bsc#12345
Acked-by: developer@suse.com
"""
        with self.assertRaises(header.HeaderException) as cm:
            self.header = header.Checker(text)

        e = cm.exception
        self.assertEqual(1, e.errors(header.FormatError))
        self.assertEqual(1, e.errors())
