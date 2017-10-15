#!/usr/bin/python
# -*- coding: utf-8 -*-

"""
todo: cache the git-commit tag from patches based on inode and mtime
"""

def tag_get(patch, tag):
    start = "%s: " % (tag,)
    result = []
    for line in patch:
        if line.startswith(start):
            result.append(line[len(start):-1])
        # These patterns were copied from
        # quilt/scripts/patchfns.in:patch_header()
        # in the quilt sources
        elif line.startswith(("---", "***", "Index:", "diff -",)):
            break

    try:
        patch.seek(0)
    except AttributeError:
        pass

    return result
