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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Check if a commit id is already backported by a patch in "
        "series.conf.")
    parser.add_argument("rev", help="Upstream commit id.")
    args = parser.parse_args()

    if not lib.check_series():
        sys.exit(1)

    repo_path = lib.repo_path()
    repo = pygit2.Repository(repo_path)
    try:
        commit = str(repo.revparse_single(args.rev).id)
    except KeyError:
        print("Error: revision \"%s\" not found in \"%s\"." %
              (args.rev, repo_path), file=sys.stderr)
        sys.exit(1)

    series = open("series")
    cwd = os.getcwd()
    os.chdir("patches")
    try:
        with lib.find_commit_in_series(commit, series) as patch:
            print("Commit %s already present in patch\n\t%s" % (
                commit[:12], patch.name,))
            references = " ".join(patch.get("References"))
            if references:
                print("for\n\t%s" % (references,))

            try:
                top = subprocess.check_output(
                    ("quilt", "--quiltrc", "-", "top",), cwd=cwd,
                    preexec_fn=lib.restore_signals,
                    stderr=subprocess.STDOUT).strip()
            except subprocess.CalledProcessError as err:
                if err.output == "No patches applied\n":
                    top = None
                else:
                    raise
            if top == patch.name:
                print("This is the top patch.")
            sys.exit(1)
    except lib.KSNotFound:
        pass
