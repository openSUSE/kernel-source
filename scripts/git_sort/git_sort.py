#!/usr/bin/python
# -*- coding: utf-8 -*-

from __future__ import print_function

import argparse
import collections
import os
import os.path
import pprint
import pygit2
import re
import shelve
import subprocess
import sys


class GSException(BaseException):
    pass


class GSError(GSException):
    pass


class RepoURL(object):
    k_org_canon_prefix = "git://git.kernel.org/pub/scm/linux/kernel/git/"
    proto_match = re.compile("(git|https?)://")
    ext = ".git"

    def __init__(self, url):
        k_org_prefixes = [
            "http://git.kernel.org/pub/scm/linux/kernel/git/",
            "https://git.kernel.org/pub/scm/linux/kernel/git/",
            "https://kernel.googlesource.com/pub/scm/linux/kernel/git/",
        ]
        for prefix in k_org_prefixes:
            if url.startswith(prefix):
                url = url.replace(prefix, self.k_org_canon_prefix)
                break

        if url.endswith(self.ext) and not self.proto_match.match(url):
            url = self.k_org_canon_prefix + url

        self.url = url


    def __eq__(self, other):
        return self.url == other.url


    def __hash__(self):
        return hash(self.url)


    def __repr__(self):
        return "%s" % (self.url,)


    def __str__(self):
        url = self.url
        if url.startswith(self.k_org_canon_prefix) and url.endswith(self.ext):
            url = url[len(self.k_org_canon_prefix):-1 * len(self.ext)]
        elif url == str(None):
            url = ""

        return url


class Head(object):
    def __init__(self, repo_url, rev="master"):
        self.repo_url = repo_url
        self.rev = rev


    def __eq__(self, other):
        return (self.repo_url == other.repo_url and self.rev == other.rev)


    def __hash__(self):
        return hash((self.repo_url, self.rev,))


    def __repr__(self):
        return "%s %s" % (repr(self.repo_url), self.rev,)


    def __str__(self):
        url = str(self.repo_url)
        if self.rev == "master":
            return url
        else:
            result = "%s %s" % (url, self.rev,)
            return result.strip()


# a list of each remote head which is indexed by this script
# If a commit does not appear in one of these remotes, it is considered "not
# upstream" and cannot be sorted.
# Repositories that come first in the list should be pulling/merging from
# repositories lower down in the list. Said differently, commits should trickle
# up from repositories at the end of the list to repositories higher up. For
# example, network commits usually follow "net-next" -> "net" -> "linux.git".
#
# Head(RepoURL(remote url), remote branch name)[]
# Note that "remote url" can be abbreviated if it starts with one of the usual
# kernel.org prefixes and "remote branch name" can be omitted if it is "master".
remotes = (
    Head(RepoURL("torvalds/linux.git")),
    Head(RepoURL("davem/net.git")),
    Head(RepoURL("davem/net-next.git")),
    Head(RepoURL("dledford/rdma.git"), "k.o/for-next"),
    Head(RepoURL("jejb/scsi.git"), "for-next"),
    Head(RepoURL("bp/bp.git"), "for-next"),
    Head(RepoURL("jj/linux-apparmor.git"), "v4.8-aa2.8-out-of-tree",),
    Head(RepoURL("tiwai/sound.git")),
    Head(RepoURL("powerpc/linux.git"), "next"),
    Head(RepoURL("tip/tip.git")),
    Head(RepoURL("shli/md.git")),
    Head(RepoURL("mkp/scsi.git")),
    Head(RepoURL("next/linux-next.git")),
)


class SortedEntry(object):
    def __init__(self, head, value):
        self.head = head
        self.value = value


class SortIndex(object):
    cache_version = 2


    def __init__(self, repo, skip_rebuild=False):
        self.repo = repo
        try:
            self.repo_heads = self.get_heads()
            self.history = self.get_history(skip_rebuild)
        except GSError as err:
            print("Error: %s" % (err,), file=sys.stderr)
            sys.exit(1)


    def get_heads(self):
        """
        Returns
        repo_heads[Head]
            sha1
        """
        result = collections.OrderedDict()
        repo_remotes = []
        args = ("git", "config", "--get-regexp", "^remote\..+\.url$",)
        for line in subprocess.check_output(args).splitlines():
            name, url = line.split(None, 1)
            name = name.split(".")[1]
            url = RepoURL(url)
            repo_remotes.append((name, url,))

        for head in remotes:
            for remote_name, remote_url in repo_remotes:
                if head.repo_url == remote_url:
                    rev = "remotes/%s/%s" % (remote_name, head.rev,)
                    try:
                        commit = self.repo.revparse_single(rev)
                    except KeyError:
                        raise GSError(
                            "Could not read revision \"%s\". Perhaps you need to "
                            "fetch from remote \"%s\", ie. `git fetch %s`." % (
                                rev, remote_name, remote_name,))
                    result[head] = str(commit.id)
                    break

        if remotes[0] not in result:
            # According to the urls in remotes, this is not a clone of linux.git
            # Sort according to commits reachable from the current head
            result = collections.OrderedDict(
                [(Head(RepoURL(str(None)), "HEAD"),
                  str(repo.revparse_single("HEAD").id),)])

        return result


    def rebuild_history(self):
        """
        Returns
        history[Head][]
            git hash represented as string of 40 characters
        """
        processed = []
        history = collections.OrderedDict()
        args = ["git", "log", "--topo-order", "--reverse", "--pretty=tformat:%H"]
        for head, rev in self.repo_heads.items():
            if head in history:
                raise GSException("head \"%s\" is not unique." % (head,))

            sp = subprocess.Popen(args + processed + [rev],
                                  stdout=subprocess.PIPE,
                                  stderr=subprocess.STDOUT)

            history[head] = [l.strip() for l in sp.stdout.readlines()]

            sp.communicate()
            if sp.returncode != 0:
                raise GSError("git log exited with an error:\n" +
                              "\n".join(history[head]))

            processed.append("^%s" % (rev,))

        return history


    def get_cache(self):
        """
        cache
            history[]
                (url, rev, sha1, []
                    git hash represented as string of 40 characters,)

        The cache is stored using basic types.
        """
        return shelve.open(os.path.expanduser("~/.cache/git-sort"))


    def parse_cache_history(self, cache_history):
        """
        Note that the cache history and self.history have different keys.
        """
        return collections.OrderedDict([
            (
                (Head(RepoURL(e[0]), e[1]), e[2],),
                e[3],
            ) for e in cache_history])


    def gen_cache_history(self, history):
        return [(
            repr(head.repo_url), head.rev, self.repo_heads[head], log,
        ) for head, log in history.items()]


    def get_history(self, skip_rebuild):
        rebuild = False
        cache = self.get_cache()
        try:
            if cache["version"] != self.cache_version:
                rebuild = True
        except KeyError:
            rebuild = True

        if not rebuild:
            c_history = self.parse_cache_history(cache["history"])
            if c_history.keys() != self.repo_heads.items():
                rebuild = True

        if rebuild:
            if skip_rebuild:
                history = None
            else:
                history = self.rebuild_history()
                cache["version"] = self.cache_version
                cache["history"] = self.gen_cache_history(history)
                # clean older cache format
                if "heads" in cache:
                    del cache["heads"]
        else:
            history = collections.OrderedDict(
                [(key[0], log,) for key, log in c_history.items()])
        cache.close()

        return history


    def sort(self, mapping):
        for head in self.repo_heads:
            for commit in self.history[head]:
                try:
                    yield SortedEntry(head, mapping.pop(commit),)
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
        cache = index.get_cache()
        try:
            version = cache["version"]
        except KeyError:
            print("No usable cache")
        else:
            print("Cached heads (version %d):" % version)
            if version == index.cache_version:
                c_history = index.parse_cache_history(cache["history"])
                pprint.pprint(c_history.keys())
            else:
                print("(omitted)")
        print("Current heads (version %d):" % index.cache_version)
        pprint.pprint(index.repo_heads.items())
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
