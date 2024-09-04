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
import io
import os
import os.path
import shutil
import subprocess
import sys
import tempfile

from git_sort import pygit2_wrapper as pygit2
from suse_git.patch import Patch
from git_sort import series_conf
from git_sort import lib
from suse_git import exc


def format_import(references, tmpdir, dstdir, rev, poi=[]):
    assert len(poi) == 0 # todo
    args = ("git", "format-patch", "--output-directory", tmpdir, "--notes",
            "--max-count=1", "--subject-prefix=", "--no-numbered", rev,)
    src = subprocess.check_output(args).decode().strip()
    # remove number prefix
    name = os.path.basename(src)[5:]
    dst = os.path.join(dstdir, name)
    if os.path.exists(os.path.join("patches", dst)):
        name = "%s-%s.patch" % (name[:-6], rev[:8],)
        dst = os.path.join(dstdir, name)

    subprocess.check_call([lib.bindir / 'clean_header.sh',
                           "--commit=%s" % rev, "--reference=%s" % references,
                           src])
    subprocess.check_call(("quilt", "import", "-P", dst, src,))
    # This will remind the user to run refresh_patch.sh
    target_dir = os.path.join(".pc", dstdir)
    if not os.path.isdir(target_dir):
        os.mkdir(target_dir)
    lib.touch(os.path.join(".pc", "%s~refresh" % (dst,)))

    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate a patch from a git commit and import it into quilt.")
    parser.add_argument("-r", "--references",
                        help="bsc# or FATE# number used to tag the patch file.")
    parser.add_argument("-d", "--destination",
                        help="Destination \"patches.xxx\" directory.")
    parser.add_argument("-f", "--followup", action="store_true",
                        help="Reuse references and destination from the patch "
                        "containing the commit specified in the first "
                        "\"Fixes\" tag in the commit log of the commit to "
                        "import.")
    parser.add_argument("rev", help="Upstream commit id to import.")
    parser.add_argument("poi", help="Limit patch to specified paths.",
                        nargs=argparse.REMAINDER)
    args = parser.parse_args()

    if not (args.references and args.destination or args.followup):
        print("Error: you must specify --references and --destination or "
              "--followup.", file=sys.stderr)
        sys.exit(1)

    if (args.references or args.destination) and args.followup:
        print("Warning: --followup overrides information from --references and "
              "--destination.", file=sys.stderr)

    if not lib.check_series():
        sys.exit(1)

    repo_path = lib.repo_path()
    if "GIT_DIR" not in os.environ:
        os.environ["GIT_DIR"] = repo_path
    repo = pygit2.Repository(repo_path)
    try:
        commit = repo.revparse_single(args.rev)
    except ValueError:
        print("Error: \"%s\" is not a valid revision." % (args.rev,),
              file=sys.stderr)
        sys.exit(1)
    except KeyError:
        print("Error: revision \"%s\" not found in \"%s\"." %
              (args.rev, repo_path), file=sys.stderr)
        sys.exit(1)

    if args.followup:
        with Patch(io.BytesIO(commit.message.encode())) as patch:
            try:
                fixes = series_conf.firstword(patch.get("Fixes")[0])
            except IndexError:
                print("Error: no \"Fixes\" tag found in commit \"%s\"." %
                      (str(commit.id)[:12]), file=sys.stderr)
                sys.exit(1)
        fixes = str(repo.revparse_single(fixes).id)

        series = open("series")
        cwd = os.getcwd()
        os.chdir("patches")
        try:
            with series_conf.find_commit(fixes, series) as (name, patch,):
                destination = os.path.dirname(name)
                references = " ".join(patch.get("References"))
        except exc.KSNotFound:
            print("Error: no patch found which contains commit %s." %
                  (fixes[:12],), file=sys.stderr)
            sys.exit(1)
        os.chdir(cwd)

        print("Info: using references \"%s\" from patch \"%s\" which contains "
              "commit %s." % (references, name, fixes[:12]))
    else:
        destination = args.destination
        references = args.references

    tmpdir = tempfile.mkdtemp(prefix="qcp.")
    try:
        result = format_import(references, tmpdir, destination, str(commit.id),
                               args.poi)
    finally:
        shutil.rmtree(tmpdir)
    sys.exit(result)
