#!/usr/bin/python
# -*- coding: utf-8 -*-

from __future__ import print_function

import argparse
import os
import os.path
import pygit2
import subprocess
import sys

import lib
import lib_tag


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Check if a commit id is already backported by a patch in "
        "series.conf.")
    parser.add_argument("rev", help="Upstream commit id.")
    args = parser.parse_args()

    if not lib.check_series():
        sys.exit(1)

    repo = pygit2.Repository(lib.repo_path())
    commit = str(repo.revparse_single(args.rev).id)

    f = lib.find_commit_in_series(commit, open("series"))
    if f is not None:
        # remove "patches/" prefix
        print("Commit %s already present in patch\n\t%s" % (
            commit[:12], f.name[8:],))
        references = " ".join(lib_tag.tag_get(f, "References"))
        if references:
            print("for\n\t%s" % (references,))

        top = subprocess.check_output(
            ("quilt", "top",), preexec_fn=lib.restore_signals).strip()
        if top == f.name:
            print("This is the top patch.")
        sys.exit(1)
