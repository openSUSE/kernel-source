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
import subprocess
import sys
from git_sort import lib
from suse_git import exc


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Print the quilt push or pop command required to reach the "
        "position where the specified commit should be imported.")
    parser.add_argument("rev", help="Upstream commit id.")
    args = parser.parse_args()

    if not lib.check_series():
        sys.exit(1)

    try:
        top = subprocess.check_output(
            ("quilt", "--quiltrc", "-", "top",),
            stderr=subprocess.STDOUT).decode().strip()
    except subprocess.CalledProcessError as err:
        if err.output.decode() == "No patches applied\n":
            top = None
        else:
            raise

    series = open("series")
    os.chdir("patches")

    try:
        (name, delta,) = lib.sequence_insert(series, args.rev, top)
    except exc.KSException as err:
        print("Error: %s" % (err,), file=sys.stderr)
        sys.exit(1)

    if delta > 0:
        print("push %d" % (delta,))
    elif delta < 0:
        print("pop %d" % (-1 * delta,))
