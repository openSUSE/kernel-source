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

from pathlib import Path
import collections
import subprocess
import operator
import tempfile
import pathlib
import signal
import shelve
import shutil
import sys
import os
import re

from . import pygit2_wrapper as pygit2
from . import series_conf
from . import git_sort
from suse_git.patch import Patch
from suse_git import exc

# fixups for python 3.6, works flawlessly in python 3.11
if sys.version_info.minor < 11:  # SLE15
    _shelve_open = shelve.open
    def _fix_shelve(*args, **kwargs):
        args = [str(a) if isinstance(a, pathlib.PurePath) else a for a in args]
        return _shelve_open(*args, **kwargs)

    shelve.open = _fix_shelve

    if sys.version_info.minor >= 6:
        class _FixPopen(subprocess.Popen):
            def __init__(self, *args, **kwargs):
                args = [str(a) if isinstance(a, pathlib.PurePath) else a for a in args]
                super().__init__(*args, **kwargs)

    else:  # SLE12
        class _FixPopen(subprocess.Popen):
            def __init__(self, *args, **kwargs):
                args = [str(a) if isinstance(a, pathlib.PurePath) else a if not isinstance(a, list) else [str(elt) if isinstance(elt, pathlib.PurePath) else elt for elt in a ] for a in args]
                new_kwargs = {}
                for key in kwargs:
                    value = kwargs[key]
                    new_kwargs[key] = str(value) if isinstance(value, pathlib.PurePath) else value
                super().__init__(*args, **new_kwargs)

        def _write_text(self, text):
            with self.open('w') as f: f.write(text)

        pathlib.PurePath.write_text = _write_text

        def _read_text(self):
            with self.open() as f: return f.read()

        pathlib.PurePath.read_text = _read_text

        _os_stat = os.stat
        def _fix_stat(*args, **kwargs):
            args = [str(a) if isinstance(a, pathlib.PurePath) else a for a in args]
            return _os_stat(*args, **kwargs)

        os.stat = _fix_stat

        _shutil_copy = shutil.copy
        def _fix_copy(*args, **kwargs):
            args = [str(a) if isinstance(a, pathlib.PurePath) else a for a in args]
            return _shutil_copy(*args, **kwargs)

        shutil.copy = _fix_copy

        _shutil_rmtree = shutil.rmtree
        def _fix_rmtree(*args, **kwargs):
            args = [str(a) if isinstance(a, pathlib.PurePath) else a for a in args]
            return _shutil_rmtree(*args, **kwargs)

        shutil.rmtree = _fix_rmtree

        _tempfile_mkstemp = tempfile.mkstemp
        def _fix_mkstemp(*args, **kwargs):
            args = [str(a) if isinstance(a, pathlib.PurePath) else a for a in args]
            new_kwargs = {}
            for key in kwargs:
                value = kwargs[key]
                new_kwargs[key] = str(value) if isinstance(value, pathlib.PurePath) else value
            return _tempfile_mkstemp(*args, **new_kwargs)

        tempfile.mkstemp = _fix_mkstemp

    subprocess.Popen = _FixPopen


# https://stackoverflow.com/a/952952
flatten = lambda l: [item for sublist in l for item in sublist]
bindir = Path(__file__).parents[2] / 'git_sort'
gs_path = bindir / 'git_sort_debug'
ss_path = bindir / 'series_sort'
si_path = bindir / 'series_insert'
qm_path = bindir / 'quilt-mode.sh'
pc_path = bindir / 'pre-commit.sh'


# http://stackoverflow.com/questions/1158076/implement-touch-using-python
def touch(fname, times=None):
    with open(fname, 'a'):
        os.utime(fname, times)


def check_series():
    """
    Check that the "series" file used by quilt looks like a series.conf file and
    not a simplified version. If using the modified quilt, it will be a symlink
    to the actual "series.conf" file and doing things like `quilt import` will
    automatically update series.conf.
    """
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
                                stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as err:
        if err.output.decode() == "No patches applied\n":
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
    """
    Get the path to the git_dir of the mainline linux git repository to use.
    Typically obtained from the LINUX_GIT environment variable.
    """
    try:
        search_path = subprocess.check_output(bindir / '..' / 'linux_git.sh').decode().strip()
    except subprocess.CalledProcessError:
        print("Error: Could not determine mainline linux git repository path.",
              file=sys.stderr)
        sys.exit(1)
    return pygit2.discover_repository(search_path)


def series_header(series):
    """
    Return the block of lines at the top of series that are not patch files
    entries or automatically generated comments. These lines should be prepended
    to the output.
    """
    header = []

    for line in series:
        if series_conf.filter_patches(line):
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
    if series_header(series) == series:
        return []
    return series_header(reversed(series))


def parse_section_header(line):
    """
    Parse a series.conf line to identify if it's a comment denoting the
    beginning of a subsystem section. In that case, return the Head object it
    corresponds to.
    """
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


def patches_per_section(inside_lines):
    """
    Returns an OrderedDict
    result[Head][]
        patch file name
    """
    result = collections.OrderedDict([
        (head, [],)
        for head in flatten((git_sort.remotes, (git_sort.oot,),))])

    current_head = git_sort.remotes[0]
    for line in inside_lines:
        try:
            current_head = parse_section_header(line)
        except exc.KSNotFound:
            pass

        if not series_conf.filter_patches(line):
            continue

        name = series_conf.firstword(line)
        result[current_head].append(name)

    for head, names in list(result.items()):
        if not names:
            del result[head]

    return result


def parse_inside(index, inside_lines, move_upstream):
    """
    Parse series.conf lines to generate InputEntry objects.
    """
    result = []
    for head, names in patches_per_section(inside_lines).items():
        for name in names:
            entry = InputEntry("\t%s\n" % (name,))
            entry.from_patch(index, name, head, move_upstream)
            result.append(entry)

    return result


def list_moved_patches(base_lines, remote_lines):
    """
    Return a list of patch file names which are in different subsystem sections
    between base and remote.
    """
    base = {}
    result = []

    for head, names in patches_per_section(base_lines).items():
        for name in names:
            base[name] = head

    for head, names in patches_per_section(remote_lines).items():
        for name in names:
            if name in base and head != base[name]:
                result.append(name)

    return result


class InputEntry(object):
    """
    A patch line entry (usually from series.conf) and associated data about the
    commit it backports.
    """
    commit_match = re.compile("[0-9a-f]{40}")


    def __init__(self, value):
        """
        value is typically a series.conf line but can be anything.
        """
        self.value = value


    def from_patch(self, index, name, current_head, move_upstream):
        """
        This is where we decide a patch line's fate in the sorted series.conf
        The following factors determine how a patch is sorted:
        * commit found in index
        * patch's series.conf current_head is indexed (ie. the local repo
          fetches from that remote)
        * patch appears to have moved downstream/didn't move/upstream
        * patch's tag is good ("Git-repo:" == current_head.url)
        * patches may be moved upstream between subsystem sections
        """
        self.name = name
        if not os.path.exists(name):
            raise exc.KSError("Could not find patch \"%s\"" % (name,))

        with Patch(open(name, mode="rb")) as patch:
            mainline_tags = patch.get("Patch-mainline")
            commit_tags = patch.get("Git-commit")
            repo_tags = patch.get("Git-repo")

        if len(repo_tags) > 1:
            raise exc.KSError("Multiple Patch-mainline tags found. Patch \"%s\" is "
                          "tagged improperly." % (name,))

        if not mainline_tags:
            raise exc.KSError(
                "There is a problem with patch \"%s\". "
                "The Patch-mainline tag is missing." % (
                    name,))

        if not commit_tags:
            self.dest_head = git_sort.oot
            mainline = mainline_tags[0]
            if re.match("^(v[1-9]|Queued)", mainline, re.IGNORECASE):
                raise exc.KSError(
                    "There is a problem with patch \"%s\". "
                    "The Patch-mainline tag \"%s\" requires Git-commit." % (
                        name, mainline,))
            if not re.match("^(Submitted|Not yet)", mainline, re.IGNORECASE):
                raise exc.KSError(
                    "There is a problem with patch \"%s\". "
                    "The Patch-mainline tag \"%s\" is not supported in sorted "
                    "section. Please add the patches without a commit id that "
                    "are neither 'Submitted' nor 'Not yet' submitted to the "
                    "manually maintained section below sorted section." % (
                        name, mainline,))
            return
        elif re.match("^(Not yet)", mainline_tags[0], re.IGNORECASE):
            print("Ignoring Git-commit since patch is out-of-tree "
                  "(\"Patch-mainline: %s\")" % (mainline_tags[0],))
            self.dest_head = git_sort.oot
            return

        class BadTag(Exception):
            pass

        def get_commit(value):
            if not value:
                raise BadTag(value)
            tag = series_conf.firstword(value)
            if not self.commit_match.match(tag):
                raise BadTag(tag)
            return tag

        try:
            self.revs = [get_commit(value) for value in commit_tags]
        except BadTag as e:
            raise exc.KSError("Git-commit tag \"%s\" in patch \"%s\" is not a "
                              "valid revision." % (e.args[0], name,))
        rev = self.revs[0]

        if len(repo_tags) > 1:
            raise exc.KSError("Multiple Git-repo tags found. Patch \"%s\" is "
                          "tagged improperly." % (name,))
        elif repo_tags:
            repo = git_sort.RepoURL(repo_tags[0])
        elif commit_tags:
            repo = git_sort.remotes[0].repo_url
        self.new_url = None

        try:
            ic = index.lookup(rev)
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
                        "\"scripts/git_sort/git_sort.yaml\" and commit the "
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
            msg_bad_tag = "There is a problem with patch \"%s\". " \
                    "The Git-repo tag is incorrect or the patch is in " \
                    "the wrong section of series.conf. Manual " \
                    "intervention is required." % (name,)
            if current_head not in index.repo_heads: # repo not indexed
                if ic.head > current_head: # patch moved downstream
                    if repo == current_head.repo_url: # good tag
                        self.dest_head = current_head
                    else: # bad tag
                        raise exc.KSError(msg_bad_tag)
                elif ic.head == current_head: # patch didn't move
                    raise exc.KSException(
                        "Head \"%s\" is not available locally but commit "
                        "\"%s\" found in patch \"%s\" was found in that head." %
                        (ic.head, rev, name,))
                elif ic.head < current_head: # patch moved upstream
                    if move_upstream: # move patches between subsystem sections
                        self.dest_head = ic.head
                        self.dest = ic
                        if repo != ic.head.repo_url: # bad tag
                            self.new_url = ic.head.repo_url
                    else: # do not move patches between subsystem sections
                        if repo == current_head.repo_url: # good tag
                            self.dest_head = current_head
                        else: # bad tag
                            raise exc.KSError(msg_bad_tag)
            else: # repo is indexed
                if ic.head > current_head: # patch moved downstream
                    if repo == current_head.repo_url: # good tag
                        raise exc.KSError(
                            "There is a problem with patch \"%s\". "
                            "The patch is in the wrong section of series.conf "
                            "or the remote fetching from \"%s\" needs to be "
                            "fetched or the relative order of \"%s\" and "
                            "\"%s\" in \"remotes\" is incorrect. Manual "
                            "intervention is required." % (
                                name, current_head.repo_url, ic.head,
                                current_head,))
                    else: # bad tag
                        raise exc.KSError(
                            "There is a problem with patch \"%s\". "
                            "The patch is in the wrong section of series.conf "
                            "or the remote fetching from \"%s\" needs to be "
                            "fetched. Manual intervention is required." % (
                                name, current_head.repo_url,))
                elif ic.head == current_head: # patch didn't move
                    self.dest_head = ic.head
                    self.dest = ic
                    if repo != ic.head.repo_url: # bad tag
                        self.new_url = ic.head.repo_url
                elif ic.head < current_head: # patch moved upstream
                    if move_upstream: # move patches between subsystem sections
                        self.dest_head = ic.head
                        self.dest = ic
                        if repo != ic.head.repo_url: # bad tag
                            self.new_url = ic.head.repo_url
                    else: # do not move patches between subsystem sections
                        if repo == current_head.repo_url: # good tag
                            self.dest_head = current_head
                            self.dest = ic
                        else: # bad tag
                            raise exc.KSError(msg_bad_tag)


def series_sort(index, entries):
    """
    entries is a list of InputEntry objects

    Returns an OrderedDict
    result[Head][]
        patch file name

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
            result[entry.dest_head][entry.dest].append(entry.value)
        except AttributeError:
            # no entry.dest
            result[entry.dest_head].append(entry.value)

    mainline = git_sort.remotes[0]
    if mainline not in index.repo_heads:
        raise exc.KSError(
            "Did not find mainline information (ref \"%s\" from the repository "
            "at \"%s\") in the repository at LINUX_GIT (\"%s\"). For more "
            "information, please refer to the \"Configuration Requirements\" "
            "section of \"scripts/git_sort/README.md\"." % (
                mainline.rev, mainline.repo_url.url, index.repo.path,))

    for head in index.repo_heads:
        result[head] = flatten([
            e[1]
            for e in sorted(result[head].items(), key=operator.itemgetter(0))])

    for head, lines in list(result.items()):
        if not lines:
            del result[head]

    return result


def series_format(entries):
    """
    entries is an OrderedDict, typically the output of series_sort()
    result[Head][]
        patch file name
    """
    result = []

    for head, lines in entries.items():
        if head != git_sort.remotes[0]:
            if result:
                result.append("\n")
            result.append("\t# %s\n" % (str(head),))
        result.extend(lines)

    return result


def tag_needs_update(entry):
    if entry.dest_head != git_sort.oot and entry.new_url is not None:
        return True
    else:
        return False


def update_tags(index, entries):
    """
    Update the Git-repo tag (possibly by removing it) of patches.
    """
    for entry in entries:
        with Patch(open(entry.name, mode="r+b")) as patch:
            message = "Failed to update tag \"%s\" in patch \"%s\". This " \
                    "tag is not found."
            if entry.dest_head == git_sort.remotes[0]:
                tag_name = "Patch-mainline"
                try:
                    patch.change(tag_name, index.describe(entry.dest.index))
                except KeyError:
                    raise exc.KSNotFound(message % (tag_name, entry.name,))
                except git_sort.GSError as err:
                    raise exc.KSError("Failed to update tag \"%s\" in patch "
                                      "\"%s\". %s" % (tag_name, entry.name,
                                                      str(err),))
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
        new_entry.dest = index.lookup(commit)
    except git_sort.GSKeyError:
        raise exc.KSError(
            "Commit %s not found in git-sort index. If it is from a "
            "repository and branch pair which is not listed in \"remotes\", "
            "please add it and submit a patch." % (commit,))
    new_entry.dest_head = new_entry.dest.head

    try:
        before, inside, after = series_conf.split(series)
    except exc.KSNotFound as err:
        raise exc.KSError(err)
    before, after = map(series_conf.filter_series, (before, after,))
    current_patches = flatten([before, series_conf.filter_series(inside), after])

    if top is None:
        top_index = 0
    else:
        top_index = current_patches.index(top) + 1

    input_entries = parse_inside(index, inside, False)
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
