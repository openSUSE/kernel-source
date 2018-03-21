#!/usr/bin/python
# -*- coding: utf-8 -*-

from __future__ import print_function

import collections
import contextlib
import operator
import os
import os.path
import pygit2
import re
import signal
import subprocess
import sys

import exc
import git_sort
import series_conf
import tag


# https://stackoverflow.com/a/952952
flatten = lambda l: [item for sublist in l for item in sublist]


# http://stackoverflow.com/questions/1158076/implement-touch-using-python
def touch(fname, times=None):
    with open(fname, 'a'):
        os.utime(fname, times)


# http://stackoverflow.com/questions/22077881/yes-reporting-error-with-subprocess-communicate
def restore_signals(): # from http://hg.python.org/cpython/rev/768722b2ae0a/
    signals = ('SIGPIPE', 'SIGXFZ', 'SIGXFSZ')
    for sig in signals:
        if hasattr(signal, sig):
            signal.signal(getattr(signal, sig), signal.SIG_DFL)


def firstword(value):
    return value.split(None, 1)[0]


def libdir():
    return os.path.dirname(os.path.realpath(__file__))


def check_series():
    def check():
        return (open("series").readline().strip() ==
                "# Kernel patches configuration file")

    try:
        retval = check()
    except IOError as err:
        print("Error: could not read series file: %s" % (err,), file=sys.stderr)
        return False

    if retval:
        return True
    
    try:
        subprocess.check_output(("quilt", "--quiltrc", "-", "top",),
                                preexec_fn=restore_signals,
                                stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as err:
        if err.output == "No patches applied\n":
            pass
        else:
            raise
    if check():
        return True
    else:
        print("Error: series file does not look like series.conf. "
              "Make sure you are using the modified `quilt`; see "
              "scripts/git_sort/README.md.", file=sys.stderr)
        return False


def repo_path():
    try:
        search_path = subprocess.check_output(
            os.path.join(libdir(), "..", "linux_git.sh"),
            preexec_fn=restore_signals).strip()
    except subprocess.CalledProcessError:
        print("Error: Could not determine mainline linux git repository path.",
              file=sys.stderr)
        sys.exit(1)
    return pygit2.discover_repository(search_path)


def filter_patches(line):
    line = line.strip()

    if line == "" or line.startswith(("#", "-", "+",)):
        return False
    else:
        return True


@contextlib.contextmanager
def find_commit_in_series(commit, series):
    """
    Caller must chdir to where the entries in series can be found.
    """
    for name in [firstword(l) for l in series if filter_patches(l)]:
        patch = tag.Patch(name)
        found = False
        if commit in [firstword(value) for value in patch.get("Git-commit")]:
            found = True
            yield patch
        patch.close()
        if found:
            return
    raise exc.KSNotFound()


def series_header(series):
    header = []

    for line in series:
        if filter_patches(line):
            break

        try:
            parse_section_header(line)
        except exc.KSNotFound:
            pass
        else:
            break

        header.append(line)

    return header


def series_footer(series):
    return series_header(reversed(series))


def parse_section_header(line):
    oot_text = git_sort.oot.rev
    line = line.strip()

    if not line.startswith("# "):
        raise exc.KSNotFound()
    line = line[2:]
    if line == oot_text:
        return git_sort.oot
    elif line.lower() == series_conf.start_text:
        raise exc.KSNotFound()

    words = line.split(None, 3)
    if len(words) > 2:
        raise exc.KSError(
            "Section comment \"%s\" in series.conf could not be parsed. "
            "series.conf is invalid." % (line,))
    args = [git_sort.RepoURL(words[0])]
    if len(words) == 2:
        args.append(words[1])

    head = git_sort.Head(*args)

    if head not in git_sort.remotes:
        raise exc.KSError(
            "Section comment \"%s\" in series.conf does not match any Head in "
            "variable \"remotes\". series.conf is invalid." % (line,))
    
    return head


def parse_inside(index, inside):
    result = []
    current_head = git_sort.remotes[0]
    for line in inside:
        try:
            current_head = parse_section_header(line)
        except exc.KSNotFound:
            pass

        if not filter_patches(line):
            continue

        name = firstword(line)
        entry = InputEntry("\t%s\n" % (name,))
        entry.from_patch(index, name, current_head)
        result.append(entry)
    return result


class InputEntry(object):
    commit_match = re.compile("[0-9a-f]{40}")


    def __init__(self, value):
        """
        value is typically a series.conf line but can be anything.
        """
        self.value = value


    def from_patch(self, index, name, current_head):
        self.name = name
        if not os.path.exists(name):
            raise exc.KSError("Could not find patch \"%s\"" % (name,))

        with tag.Patch(name) as patch:
            commit_tags = patch.get("Git-commit")
            repo_tags = patch.get("Git-repo")

        if not commit_tags:
            self.dest_head = git_sort.oot
            return

        self.revs = [firstword(ct) for ct in commit_tags]
        for rev in self.revs:
            if not self.commit_match.match(rev):
                raise exc.KSError("Git-commit tag \"%s\" in patch \"%s\" is not a "
                              "valid revision." % (rev, name,))
        rev = self.revs[0]

        if len(repo_tags) > 1:
            raise exc.KSError("Multiple Git-repo tags found. Patch \"%s\" is "
                          "tagged improperly." % (name,))
        elif repo_tags:
            repo = git_sort.RepoURL(repo_tags[0])
        elif commit_tags:
            repo = git_sort.remotes[0].repo_url
        self.new_url = None

        # this is where we decide a patch line's fate in the sorted series.conf
        try:
            head, cindex = index.lookup(rev)
        except git_sort.GSKeyError: # commit not found
            if current_head not in index.repo_heads: # repo not indexed
                if repo == current_head.repo_url: # good tag
                    self.dest_head = current_head
                else: # bad tag
                    raise exc.KSError(
                        "There is a problem with patch \"%s\". "
                        "The Git-repo tag is incorrect or the patch is in the "
                        "wrong section of series.conf and (the Git-commit tag "
                        "is incorrect or the relevant remote is outdated or "
                        "not available locally) or an entry for this "
                        "repository is missing from \"remotes\". In the last "
                        "case, please edit \"remotes\" in "
                        "\"scripts/git_sort/git_sort.py\" and commit the "
                        "result. Manual intervention is required." % (name,))
            else: # repo is indexed
                if repo == current_head.repo_url: # good tag
                    raise exc.KSError(
                        "There is a problem with patch \"%s\". "
                        "Commit \"%s\" not found in git-sort index. "
                        "The remote fetching from \"%s\" needs to be fetched "
                        "or the Git-commit tag is incorrect or the patch is "
                        "in the wrong section of series.conf. Manual "
                        "intervention is required." % (
                            name, rev, current_head.repo_url,))
                else: # bad tag
                    raise exc.KSError(
                        "There is a problem with patch \"%s\". "
                        "The Git-repo tag is incorrect or the patch is in the "
                        "wrong section of series.conf. Manual intervention is "
                        "required." % (name,))
        else: # commit found
            if current_head not in index.repo_heads: # repo not indexed
                if head > current_head: # patch moved downstream
                    if repo == current_head.repo_url: # good tag
                        self.dest_head = current_head
                    else: # bad tag
                        raise exc.KSError(
                            "There is a problem with patch \"%s\". "
                            "The Git-repo tag is incorrect or the patch is in "
                            "the wrong section of series.conf. Manual "
                            "intervention is required." % (name,))
                elif head == current_head: # patch didn't move
                    raise exc.KSException(
                        "Head \"%s\" is not available locally but commit "
                        "\"%s\" found in patch \"%s\" was found in that head." %
                        (head, rev, name,))
                elif head < current_head: # patch moved upstream
                    self.dest_head = head
                    self.cindex = cindex
                    if repo != head.repo_url: # bad tag
                        self.new_url = head.repo_url
            else: # repo is indexed
                if head > current_head: # patch moved downstream
                    if repo == current_head.repo_url: # good tag
                        raise exc.KSError(
                            "There is a problem with patch \"%s\". "
                            "The patch is in the wrong section of series.conf "
                            "or the remote fetching from \"%s\" needs to be "
                            "fetched or the relative order of \"%s\" and "
                            "\"%s\" in \"remotes\" is incorrect. Manual "
                            "intervention is required." % (
                                name, current_head.repo_url, head,
                                current_head,))
                    else: # bad tag
                        raise exc.KSError(
                            "There is a problem with patch \"%s\". "
                            "The patch is in the wrong section of series.conf "
                            "or the remote fetching from \"%s\" needs to be "
                            "fetched. Manual intervention is required." % (
                                name, current_head.repo_url,))
                elif head == current_head: # patch didn't move
                    self.dest_head = head
                    self.cindex = cindex
                    if repo != head.repo_url: # bad tag
                        self.new_url = head.repo_url
                elif head < current_head: # patch moved upstream
                    self.dest_head = head
                    self.cindex = cindex
                    if repo != head.repo_url: # bad tag
                        self.new_url = head.repo_url


def series_sort(index, entries):
    """
    entries is a list of InputEntry objects

    Returns an OrderedDict
        result[Head][]
            series.conf line with a patch name

    Note that Head may be a "virtual head" like "out-of-tree patches".
    """
    def container(head):
        if head in index.repo_heads:
            return collections.defaultdict(list)
        else:
            return []

    result = collections.OrderedDict([
        (head, container(head),)
        for head in flatten((git_sort.remotes, (git_sort.oot,),))])

    for entry in entries:
        try:
            result[entry.dest_head][entry.cindex].append(entry.value)
        except AttributeError:
            # no entry.cindex
            result[entry.dest_head].append(entry.value)

    for head in index.repo_heads:
        result[head] = flatten([
            e[1]
            for e in sorted(result[head].items(), key=operator.itemgetter(0))])

    for head, lines in result.items():
        if not lines:
            del result[head]

    return result


def series_format(entries):
    """
    entries is an OrderedDict
        entries[Head][]
            series.conf line with a patch name
    """
    result = []

    for head, lines in entries.items():
        if head != git_sort.remotes[0]:
            result.extend(["\n", "\t# %s\n" % (str(head),)])
        result.extend(lines)

    return result


def tag_needs_update(entry):
    if entry.dest_head != git_sort.oot and entry.new_url is not None:
        return True
    else:
        return False


def update_tags(index, entries):
    for entry in entries:
        with tag.Patch(entry.name) as patch:
            message = "Failed to update tag \"%s\" in patch \"%s\". This " \
                    "tag is not found."
            if entry.dest_head == git_sort.remotes[0]:
                tag_name = "Patch-mainline"
                try:
                    patch.change(tag_name, index.describe(entry.cindex))
                except KeyError:
                    raise exc.KSNotFound(message % (tag_name, entry.name,))
                patch.remove("Git-repo")
            else:
                tag_name = "Git-repo"
                try:
                    patch.change(tag_name, repr(entry.new_url))
                except KeyError:
                    raise exc.KSNotFound(message % (tag_name, entry.name,))


def sequence_insert(series, rev, top):
    """
    top is the top applied patch, None if none are applied.

    Caller must chdir to where the entries in series can be found.

    Returns the name of the new top patch and how many must be applied/popped.
    """
    filter_series = lambda lines : [firstword(line) for line in lines
                                    if filter_patches(line)]
    git_dir = repo_path()
    repo = pygit2.Repository(git_dir)
    index = git_sort.SortIndex(repo)

    try:
        commit = str(repo.revparse_single(rev).id)
    except ValueError:
        raise exc.KSError("\"%s\" is not a valid revision." % (rev,))
    except KeyError:
        raise exc.KSError("Revision \"%s\" not found in \"%s\"." % (
            rev, git_dir,))

    marker = "# new commit"
    new_entry = InputEntry(marker)
    try:
        new_entry.dest_head, new_entry.cindex = index.lookup(commit)
    except git_sort.GSKeyError:
        raise exc.KSError(
            "Commit %s not found in git-sort index. If it is from a "
            "repository and branch pair which is not listed in \"remotes\", "
            "please add it and submit a patch." % (commit,))

    try:
        before, inside, after = series_conf.split(series)
    except exc.KSNotFound as err:
        raise exc.KSError(err)
    before, after = map(filter_series, (before, after,))
    current_patches = flatten([before, filter_series(inside), after])

    if top is None:
        top_index = 0
    else:
        top_index = current_patches.index(top) + 1

    input_entries = parse_inside(index, inside)
    input_entries.append(new_entry)

    sorted_entries = series_sort(index, input_entries)
    new_patches = flatten([
        before,
        [line.strip() for lines in sorted_entries.values() for line in lines],
        after,
    ])
    commit_pos = new_patches.index(marker)
    if commit_pos == 0:
        # should be inserted first in series
        name = ""
    else:
        name = new_patches[commit_pos - 1]
    del new_patches[commit_pos]

    if new_patches != current_patches:
        raise exc.KSError("Subseries is not sorted. "
                      "Please run scripts/series_sort.py.")

    return (name, commit_pos - top_index,)
