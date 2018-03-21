#!/usr/bin/python
# -*- coding: utf-8 -*-

"""
When we want to backport a specific commit at its right position in the sorted
sub-series, it is most efficient to use sequence_patch.sh to expand the tree up
to the patch just before where the new commit will be added. The current script
prints out which patch that is. Use in conjunction with sequence-patch.sh:
    kernel-source$ ./scripts/sequence-patch.sh $(~/programming/suse/ksapply/sequence-insert.py 5c8227d0d3b1)
"""

from __future__ import print_function

import argparse
import os
import sys

import exc
import lib


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Print the name of the patch over which the specified "
        "commit should be imported.")
    parser.add_argument("rev", help="Upstream commit id.")
    args = parser.parse_args()

    try:
        (name, delta,) = lib.sequence_insert(open("series.conf"), args.rev,
                                             None)
    except exc.KSException as err:
        print("Error: %s" % (err,), file=sys.stderr)
        sys.exit(1)

    print(name)
