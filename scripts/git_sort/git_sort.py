#!/usr/bin/python
# -*- coding: utf-8 -*-

from __future__ import print_function

import argparse
import os
import os.path
import pprint
import pygit2
import shelve
import subprocess
import sys

# a list of each remote head which is indexed by this script
# If a commit does not appear in one of these remotes, it is considered "not
# upstream" and cannot be sorted.
# Repositories that come first in the list should be pulling/merging from
# repositories lower down in the list. Said differently, commits should trickle
# up from repositories at the end of the list to repositories higher up. For
# example, network commits usually follow "net-next" -> "net" -> "linux.git".
# (canonical remote url, remote branch name)
# The canonical url is the one on git://git.kernel.org, if it exists.
remotes = (
    ("git://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git",
     "master",),
    ("git://git.kernel.org/pub/scm/linux/kernel/git/davem/net.git",
     "master",),
    ("git://git.kernel.org/pub/scm/linux/kernel/git/davem/net-next.git",
     "master",),
    ("git://git.kernel.org/pub/scm/linux/kernel/git/dledford/rdma.git",
     "k.o/for-next",),
    ("git://git.kernel.org/pub/scm/linux/kernel/git/jejb/scsi.git",
     "for-next",),
    ("git://git.kernel.org/pub/scm/linux/kernel/git/bp/bp.git",
     "for-next",),
    ("git://git.kernel.org/pub/scm/linux/kernel/git/jj/linux-apparmor.git",
     "v4.8-aa2.8-out-of-tree",),
    ("git://git.kernel.org/pub/scm/linux/kernel/git/tiwai/sound.git",
     "master",),
    ("git://git.kernel.org/pub/scm/linux/kernel/git/powerpc/linux.git",
     "next",),
    ("git://git.kernel.org/pub/scm/linux/kernel/git/tip/tip.git",
     "master",),
    ("git://git.kernel.org/pub/scm/linux/kernel/git/next/linux-next.git",
     "master",),
)


class GSException(BaseException):
    pass


class GSError(GSException):
    pass


k_org_canon_prefix = "git://git.kernel.org/pub/scm/linux/kernel/git/"

def cmp_url(canonical_url, remote_url):
    k_org_prefixes = [
        "https://git.kernel.org/pub/scm/linux/kernel/git/",
        "https://kernel.googlesource.com/pub/scm/linux/kernel/git/",
    ]

    for prefix in k_org_prefixes:
        if remote_url.startswith(prefix):
            remote_url = remote_url.replace(
                prefix, k_org_canon_prefix)
            break

    return cmp(canonical_url, remote_url)


def head_name(canonical_url, branch_name):
    assert(canonical_url.startswith(k_org_canon_prefix))
    ext = ".git"
    assert(canonical_url.endswith(ext))

    repo_name = canonical_url[len(k_org_canon_prefix):-1 * len(ext)]
    if branch_name == "master":
        return repo_name
    else:
        return "%s %s" % (repo_name, branch_name,)


class SortedEntry(object):
    def __init__(self, head_name, value):
        self.head_name = head_name
        self.value = value


    def __repr__(self):
        return "%s = %s" % (self.head_name, pprint.pformat(self.value),)


class SortIndex(object):
    def __init__(self, repo, skip_rebuild=False):
        self.repo = repo
        try:
            self.heads = self.get_heads()
            self.history = self.get_history(skip_rebuild)
        except GSError as err:
            print("Error: %s" % (err,), file=sys.stderr)
            sys.exit(1)


    def get_heads(self):
        """
        Returns (head name, sha1)[]
        """
        heads = []
        repo_remotes = {}
        args = ("git", "config", "--get-regexp", "^remote\..+\.url$",)
        for line in subprocess.check_output(args).splitlines():
            name, url = line.split(None, 1)
            name = name.split(".")[1]
            repo_remotes[url] = name

        for canon_url, branch_name in remotes:
            for remote_url, remote_name in repo_remotes.items():
                if cmp_url(canon_url, remote_url) == 0:
                    rev = "%s/%s" % (remote_name, branch_name,)
                    try:
                        commit = self.repo.revparse_single(rev)
                    except KeyError:
                        raise GSError(
                            "Could not read revision \"%s\". Perhaps you need to "
                            "fetch from remote \"%s\", ie. `git fetch %s`." % (
                                rev, remote_name, remote_name,))
                    heads.append((head_name(canon_url, branch_name),
                                  str(commit.id),))
                    continue

        # According to the urls in remotes, this is not a clone of linux.git
        # Sort according to commits reachable from the current head
        if not heads or heads[0][0] != head_name(*remotes[0]):
            heads = [("HEAD", str(self.repo.revparse_single("HEAD").id),)]

        return heads


    def rebuild_history(self):
        processed = []
        history = {}
        args = ["git", "log", "--topo-order", "--reverse", "--pretty=tformat:%H"]
        for head_name, rev in self.heads:
            sp = subprocess.Popen(args + processed + [rev], stdout=subprocess.PIPE,
                                  stderr=subprocess.STDOUT)

            if head_name in history:
                raise GSException("head name \"%s\" is not unique." %
                                  (head_name,))

            history[head_name] = [l.strip() for l in sp.stdout.readlines()]

            sp.communicate()
            if sp.returncode != 0:
                raise GSError("git log exited with an error:\n" +
                              "\n".join(history[head_name]))

            processed.append("^%s" % (rev,))

        return history


    def get_cache(self):
        return shelve.open(os.path.expanduser("~/.cache/git-sort"))


    def get_history(self, skip_rebuild):
        """
        cache
            heads[]
                (head name, sha1)
            history[head name][]
                git hash represented as string of 40 characters
        """
        rebuild = False
        cache = self.get_cache()
        try:
            c_heads = cache["heads"]
        except KeyError:
            rebuild = True

        if not rebuild and c_heads != self.heads:
            rebuild = True

        if rebuild:
            if skip_rebuild:
                history = None
            else:
                history = self.rebuild_history()
                cache["heads"] = self.heads
                cache["history"] = history
        else:
            history = cache["history"]
        cache.close()

        return history


    def sort(self, mapping):
        for head_name, rev in self.heads:
            for commit in self.history[head_name]:
                try:
                    yield SortedEntry(head_name, mapping.pop(commit),)
                except KeyError:
                    pass

        return


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Sort input lines according to the upstream order of "
        "commits that each line represents, with the first word on the line "
        "taken to be a commit id.")
    parser.add_argument("-d", "--dump-heads", action="store_true",
                        help="Print the branch heads used for sorting "
                        "(debugging).")
    args = parser.parse_args()

    try:
        path = os.environ["GIT_DIR"]
    except KeyError:
        path = pygit2.discover_repository(os.getcwd())
    repo = pygit2.Repository(path)
    index = SortIndex(repo, skip_rebuild=args.dump_heads)

    if args.dump_heads:
        print("Cached heads:")
        cache = index.get_cache()
        try:
            c_heads = cache["heads"]
        except KeyError:
            c_heads = None
        pprint.pprint(c_heads)
        print("Current heads:")
        try:
            heads = index.heads
        except GSError as err:
            print("Error: %s" % (err,), file=sys.stderr)
            sys.exit(1)
        pprint.pprint(heads)
        if index.history:
            action = "Will not"
        else:
            action = "Will"
        print("%s rebuild history" % (action,))
        sys.exit(0)

    lines = {}
    num = 0
    for line in sys.stdin.readlines():
        num = num + 1
        try:
            commit = repo.revparse_single(line.strip().split(None, 1)[0])
        except ValueError:
            print("Error: did not find a commit hash on line %d:\n%s" %
                  (num, line.strip(),), file=sys.stderr)
            sys.exit(1)
        except KeyError:
            print("Error: commit hash on line %d not found in the repository:\n%s" %
                  (num, line.strip(),), file=sys.stderr)
            sys.exit(1)
        h = str(commit.id)
        if h in lines:
            lines[h].append(line)
        else:
            lines[h] = [line]

    print("".join([line for entry in index.sort(lines) for line in
                   entry.value]), end="")

    if len(lines) != 0:
        print("Error: the following entries were not found in the indexed heads:",
              file=sys.stderr)
        print("".join([line for line_list in lines.values() for line in
                       line_list]), end="")
        sys.exit(1)
