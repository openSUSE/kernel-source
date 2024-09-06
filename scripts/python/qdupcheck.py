#!/usr/bin/python3
# -*- coding: utf-8 -*-

# Copyright (C) 2018 SUSE LLC
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301,
# USA.

import argparse
import os
import os.path
import subprocess
import sys

from git_sort import pygit2_wrapper as pygit2
from git_sort import series_conf
from git_sort import lib
from suse_git import exc


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
        with series_conf.find_commit(commit, series) as (name, patch,):
            print("Commit %s already present in patch\n\t%s" % (
                commit[:12], name,))
            references = " ".join(patch.get("References"))
            if references:
                print("for\n\t%s" % (references,))

            try:
                top = subprocess.check_output(
                    ("quilt", "--quiltrc", "-", "top",),
                    cwd=cwd, stderr=subprocess.STDOUT,).decode().strip()
            except subprocess.CalledProcessError as err:
                if err.output.decode() == "No patches applied\n":
                    top = None
                else:
                    raise
            if top == name:
                print("This is the top patch.")
            sys.exit(1)
    except exc.KSNotFound:
        pass
