#!/usr/bin/python3
# -*- coding: utf-8 -*-

from pathlib import Path
import subprocess
import datetime
import tempfile
import pathlib
import os.path
import shelve
import shutil
import sys
import os
import re

import pygit2_wrapper as pygit2


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


# from http://www.pygit2.org/recipes/git-show.html
class FixedOffset(datetime.tzinfo):
    """Fixed offset in minutes east from UTC."""

    def __init__(self, offset):
        self.__offset = datetime.timedelta(minutes = offset)

    def utcoffset(self, dt):
        return self.__offset

    def tzname(self, dt):
        return None # we don't know the time zone's name

    def dst(self, dt):
        return datetime.timedelta(0) # we don't know about DST


def format_sanitized_subject(message):
    """
    Reimplemented from the similarly named function in the git source.
    """
    def is_title_char(c):
        if ((c >= 'a' and c <= 'z') or (c >= 'A' and c <= 'Z') or
            (c >= '0' and c <= '9') or c == '.' or c == '_'):
            return True
        else:
            return False

    result = []
    space = False
    i = 0
    end = message.find("\n")
    if end == -1:
        end = len(message)
    while i < end:
        c = message[i]
        if is_title_char(c):
            if space and result:
                result.append("-")
            result.append(c)
            space = False
            if c == ".":
                while i + 1 < end and message[i + 1] == ".":
                    i = i + 1
        else:
            space = True
        i = i + 1
    return "".join(result[:52])


def format_patch(commit, mainline=None, repo=None, references=None,
                 directory=""):
    name = Path(directory, format_sanitized_subject(commit.message) +
                        ".patch")

    with name.open('w') as f:
        f.write("From: %s <%s>\n" % (commit.author.name, commit.author.email,))
        tzinfo = FixedOffset(commit.author.offset)
        dt = datetime.datetime.fromtimestamp(float(commit.author.time), tzinfo)
        f.write("Date: %s\n" % (dt.strftime("%c %z"),))
        if mainline and repo is None:
            f.write("Patch-mainline: %s\n" % (mainline,))
            if re.match("^v", mainline):
                f.write("Git-commit: %s\n" % (str(commit.id),))
        elif mainline is None and repo:
            f.write("Patch-mainline: Queued in subsystem maintainer repository\n")
            f.write("Git-repo: %s\n" % (repo,))
            f.write("Git-commit: %s\n" % (str(commit.id),))
        else:
            f.write("Patch-mainline: Not yet, to be submitted by partner developer\n")
        if references is not None:
            f.write("References: %s\n" % (references,))
        f.write("Subject: %s" % (commit.message,))
        if not commit.message.endswith("\n"):
            f.write("\n")
            if commit.message.find("\n") == -1:
                f.write("\n")
        else:
            if commit.message.count("\n") == 1:
                # ends with a newline but consists only of a subject.
                f.write("\n")
        f.write("---\n")
        args = []
        if len(commit.parents):
            args.append(commit.parents[0].tree)
        diff = commit.tree.diff_to_tree(*args, swap=True)
        f.write(diff.stats.format(pygit2.GIT_DIFF_STATS_FULL, width=79))
        f.write("\n")
        patch = diff.patch
        if patch is not None:
            f.write(diff.patch)
        f.write("--\ngs-tests\n")

    return name


def format_series(content):
    def format_section(section):
        if section[0] is not None:
            header = "\t# %s\n" % (section[0],)
        else:
            header = ""
        return "%s%s" % (header,
                         "\n".join(["\t%s" % (name,) for name in section[1]]),)
    return \
"""	########################################################
	# sorted patches
	########################################################
%s
	########################################################
	# end of sorted patches
	########################################################
""" % (
    "\n\n".join(map(format_section, content)))

