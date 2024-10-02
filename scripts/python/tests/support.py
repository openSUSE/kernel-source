# -*- coding: utf-8 -*-

from git_sort import pygit2_wrapper as pygit2
from pathlib import Path
import datetime
import re
import os

os.environ['GIT_SORT_REPOSITORIES'] = str(Path(__file__).parent / 'git_sort.yaml')
import git_sort.lib


def testdir():
    return Path(__file__).parent


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

