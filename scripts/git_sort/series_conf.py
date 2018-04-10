#!/usr/bin/python
# -*- coding: utf-8 -*-

from __future__ import print_function

import argparse
import contextlib
import errno
import sys

import exc
import tag


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


def filter_patches(line):
    line = line.strip()

    if line == "" or line.startswith(("#", "-", "+",)):
        return False
    else:
        return True


def firstword(value):
    return value.split(None, 1)[0]


filter_series = lambda lines : [firstword(line) for line in lines
                                if filter_patches(line)]


@contextlib.contextmanager
def find_commit_in_series(commit, series):
    """
    Caller must chdir to where the entries in series can be found.
    """
    for name in filter_series(series):
        patch = tag.Patch(name)
        found = False
        if commit in [firstword(value) for value in patch.get("Git-commit")]:
            found = True
            yield patch
        patch.close()
        if found:
            return
    raise exc.KSNotFound()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Extract the sorted patches section of a series.conf file.")
    parser.add_argument("-n", "--name-only", action="store_true",
                        help="Print only patch names.")
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
        if args.name_only:
            inside = filter_series(inside)
            inside = [line + "\n" for line in inside]

        try:
            sys.stdout.writelines(inside)
            # Avoid an unsightly error that may occur when not all output is
            # read:
            # close failed in file object destructor:
            # sys.excepthook is missing
            # lost sys.stderr
            sys.stdout.flush()
        except IOError as err:
            if err.errno == errno.EPIPE:
                pass
            else:
                raise
