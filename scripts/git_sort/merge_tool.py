#!/usr/bin/python
# -*- coding: utf-8 -*-

"""
Depends on orderedset, may be installed via pip/pip2
    pip install orderedset

Depends on `merge` from rcs

Add a section like this to git config:

[mergetool "git-sort"]
	cmd = /<path>/merge_tool.py $LOCAL $BASE $REMOTE $MERGED
	trustExitCode = true

Then call
git mergetool --tool=git-sort series.conf

"""

from __future__ import print_function

from orderedset import OrderedSet
import os.path
import pygit2
import shutil
import subprocess
import sys

import lib


def splice(series, inside, output_path):
    with open(output_path, mode="w") as f:
        [f.writelines(l) for l in (
            series[0],
            lib.series_header(series[1]),
            inside,
            lib.series_footer(series[1]),
            series[2],)]


if __name__ == "__main__":
    local_path, base_path, remote_path, merged_path = sys.argv[1:5]

    repo_path = lib.repo_path()
    if "GIT_DIR" not in os.environ:
        # this is for the `git log` call in git_sort.py
        os.environ["GIT_DIR"] = repo_path
    repo = pygit2.Repository(repo_path)

    local, base, remote = (
        (s[0], s[1], s[2], OrderedSet([lib.firstword(l) for l in s[1] if
                                       lib.filter_patches(l)]),)
        for s in [
            lib.split_series(open(s_path)) for s_path in (
                local_path, base_path, remote_path,)
        ]
    )

    added = remote[3] - base[3]
    removed = base[3] - remote[3]

    added_nb = len(added)
    removed_nb = len(removed)
    if added_nb or removed_nb:
        print("%d commits added, %d commits removed from base to remote." %
              (added_nb, removed_nb,))
    dup_add_nb = len(local[3] & added)
    dup_rem_nb = len(removed) - len(local[3] & removed)
    if dup_add_nb:
        print("Warning: %d commits added in remote and already present in "
              "local, ignoring." % (dup_add_nb,))
    if dup_rem_nb:
        print("Warning: %d commits removed in remote but not present in local, "
              "ignoring." % (dup_rem_nb,))

    input_entries = []
    for patch in local[3] - removed | added:
        entry = lib.InputEntry("\t%s\n" % (patch,))
        entry.from_patch(repo, patch)
        input_entries.append(entry)
    try:
        sorted_entries = lib.series_sort(repo, input_entries)
    except lib.KSException as err:
        print("Error: %s" % (err,), file=sys.stderr)
        sys.exit(1)
    output = lib.series_format(sorted_entries)

    # If there were no conflicts outside of the sorted section, then it would be
    # sufficient to splice the sorted result into local
    splice(local, output, merged_path)

    # ... but we don't know, so splice them all and call `merge` so that the
    # lines outside the sorted section get conflict markers if needed
    splice(base, output, base_path)
    splice(remote, output, remote_path)

    retval = subprocess.call(["merge", merged_path, base_path, remote_path])
    if retval != 0:
        name = "%s.merged%d" % (merged_path, os.getpid(),)
        print("Warning: conflicts outside of sorted section, leaving merged "
              "result in %s" % (name,))
        shutil.copy(merged_path, name)
        sys.exit(1)

