#!/usr/bin/python
# -*- coding: utf-8 -*-

from __future__ import print_function

import argparse
import errno
import sys

import exc


start_text = "sorted patches"
end_text = "end of sorted patches"


def split(series):
    before = []
    inside = []
    after = []

    whitespace = []
    comments = []

    current = before
    for line in series:
        l = line.strip()

        if l == "":
            if comments:
                current.extend(comments)
                comments = []
            whitespace.append(line)
            continue
        elif l.startswith("#"):
            if whitespace:
                current.extend(whitespace)
                whitespace = []
            comments.append(line)

            if current == before and l.lower() == "# %s" % (start_text,):
                current = inside
            elif current == inside and l.lower() == "# %s" % (end_text,):
                current = after
        else:
            if comments:
                current.extend(comments)
                comments = []
            if whitespace:
                current.extend(whitespace)
                whitespace = []
            current.append(line)
    if comments:
        current.extend(comments)
        comments = []
    if whitespace:
        current.extend(whitespace)
        whitespace = []

    if current is before:
        raise exc.KSNotFound("Sorted subseries not found.")

    current.extend(comments)
    current.extend(whitespace)

    return (before, inside, after,)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Extract the sorted patches section of a series.conf file.")
    parser.add_argument("series", nargs="?", metavar="series.conf",
                        help="series.conf file. Default: read input from stdin.")
    args = parser.parse_args()

    if args.series is not None:
        f = open(args.series)
    else:
        f = sys.stdin
    lines = f.readlines()

    try:
        before, inside, after = split(lines)
    except exc.KSNotFound:
        pass
    else:
        try:
            sys.stdout.writelines(inside)
        except IOError as err:
            if err.errno == errno.EPIPE:
                pass
            else:
                raise
