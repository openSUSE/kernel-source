#!/usr/bin/python
# -*- coding: utf-8 -*-

"""
Script to sort series.conf lines according to the upstream order of commits that
the patches backport.

The script can either read series.conf lines (or a subset thereof) from stdin or
from the file named in the first argument.

A convenient way to use series_sort.py to filter a subset of lines
within series.conf when using the vim text editor is to visually
select the lines and filter them through the script:
    shift-v
    j j j j [...] # or ctrl-d or /pattern<enter>
    :'<,'>! ~/<path>/series_sort.py
"""

from __future__ import print_function

import argparse
import os
import pygit2
import sys

import lib
import tag
import git_sort


def update_tags(index, entries):
    for entry in entries:
        with tag.Patch(entry.name) as patch:
            if entry.dest_head == git_sort.remotes[0]:
                patch.change("Patch-mainline", index.describe(entry.cindex))
                patch.remove("Git-repo")
            else:
                patch.change("Git-repo", repr(entry.new_url))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Sort series.conf lines according to the upstream order of "
        "commits that the patches backport.")
    parser.add_argument("-p", "--prefix", metavar="DIR",
                        help="Search for patches in this directory. Default: "
                        "current directory.")
    parser.add_argument("-c", "--check", action="store_true",
                        help="Report via exit status 2 if the series is not "
                        "sorted.")
    parser.add_argument("series", nargs="?", metavar="series.conf",
                        help="series.conf file which will be modified in "
                        "place. Default: read input from stdin.")
    args = parser.parse_args()

    repo_path = lib.repo_path()
    repo = pygit2.Repository(repo_path)
    index = lib.git_sort.SortIndex(repo)

    if args.series is not None:
        args.series = os.path.abspath(args.series)
        f = open(args.series)
    else:
        f = sys.stdin
    lines = f.readlines()

    if args.prefix is not None:
        os.chdir(args.prefix)

    try:
        before, inside, after = lib.split_series(lines)
    except lib.KSNotFound:
        before = []
        inside = lines
        after = []

    try:
        input_entries = lib.parse_inside(index, inside)
    except lib.KSError as err:
        print("Error: %s" % (err,), file=sys.stderr)
        sys.exit(1)

    try:
        sorted_entries = lib.series_sort(index, input_entries)
    except lib.KSError as err:
        print("Error: %s" % (err,), file=sys.stderr)
        sys.exit(1)

    new_inside = lib.flatten([
        lib.series_header(inside),
        lib.series_format(sorted_entries),
        lib.series_footer(inside),
    ])

    to_update = [entry for entry in input_entries
                 if (entry.dest_head != git_sort.oot
                     and entry.new_url is not None)]
    if args.check:
        result = 0
        if inside != new_inside:
            print("Input is not sorted.")
            result = 2
        if len(to_update):
            print("Git-repo tags are outdated.")
            result = 2
        sys.exit(result)
    else:
        output = lib.flatten([
            before,
            new_inside,
            after,
        ])

        if args.series is not None:
            f = open(args.series, mode="w")
        else:
            f = sys.stdout
        f.writelines(output)
        update_tags(index, to_update)
