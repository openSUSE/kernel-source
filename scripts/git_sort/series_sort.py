#!/usr/bin/python3
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

import argparse
import os
import sys

try:
    import pygit2
except ImportError as err:
    print("Error: %s" % (err,), file=sys.stderr)
    print("Please install the \"pygit2\" python3 module. For more details, "
          "please refer to the \"Installation Requirements\" section of "
          "\"scripts/git_sort/README.md\".", file=sys.stderr)
    sys.exit(1)

import exc
import git_sort
import lib
import series_conf
import tag


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
    index = git_sort.SortIndex(repo)

    if args.series is not None:
        try:
            f = open(args.series)
        except FileNotFoundError as err:
            print("Error: %s" % (err,), file=sys.stderr)
            sys.exit(1)
        series = os.path.abspath(args.series)
    else:
        f = sys.stdin
    lines = f.readlines()

    if args.prefix is not None:
        os.chdir(args.prefix)

    try:
        before, inside, after = series_conf.split(lines)
    except exc.KSNotFound as err:
        if args.series is None:
            before = []
            inside = lines
            after = []
        elif args.check:
            # no sorted section
            sys.exit(0)
        else:
            print("Error: %s" % (err,), file=sys.stderr)
            sys.exit(1)

    try:
        input_entries = lib.parse_inside(index, inside)
    except exc.KSError as err:
        print("Error: %s" % (err,), file=sys.stderr)
        sys.exit(1)

    try:
        sorted_entries = lib.series_sort(index, input_entries)
    except exc.KSError as err:
        print("Error: %s" % (err,), file=sys.stderr)
        sys.exit(1)

    new_inside = lib.flatten([
        lib.series_header(inside),
        lib.series_format(sorted_entries),
        lib.series_footer(inside),
    ])

    to_update = list(filter(lib.tag_needs_update, input_entries))
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
            f = open(series, mode="w")
        else:
            f = sys.stdout
        f.writelines(output)
        try:
            lib.update_tags(index, to_update)
        except exc.KSError as err:
            print("Error: %s" % (err,), file=sys.stderr)
            sys.exit(1)
