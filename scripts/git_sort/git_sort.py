#!/usr/bin/python
# -*- coding: utf-8 -*-

from __future__ import print_function

import argparse
import bisect
import collections
import operator
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


class GSKeyError(GSException):
    pass


class GSNotFound(GSException):
    pass


class RepoURL(object):
    k_org_canon_prefix = "git://git.kernel.org/pub/scm/linux/kernel/git/"
    proto_match = re.compile("(git|https?)://")
    ext = ".git"

    def __init__(self, url):
        if url is None or url == repr(None):
            self.url = None
            return

        k_org_prefixes = [
            "http://git.kernel.org/pub/scm/linux/kernel/git/",
            "https://git.kernel.org/pub/scm/linux/kernel/git/",
            "https://kernel.googlesource.com/pub/scm/linux/kernel/git/",
        ]
        for prefix in k_org_prefixes:
            if url.startswith(prefix):
                url = url.replace(prefix, self.k_org_canon_prefix)
                break

        if not self.proto_match.match(url):
            url = self.k_org_canon_prefix + url

        if not url.endswith(self.ext):
            url = url + self.ext

        self.url = url


    def __eq__(self, other):
        return self.url == other.url


    def __cmp__(self, other):
        return cmp(self.url, other.url)


    def __hash__(self):
        return hash(self.url)


    def __repr__(self):
        return "%s" % (self.url,)


    def __str__(self):
        url = self.url
        if url is None:
            url = ""
        elif url.startswith(self.k_org_canon_prefix) and url.endswith(self.ext):
            url = url[len(self.k_org_canon_prefix):-1 * len(self.ext)]

        return url


class Head(object):
    def __init__(self, repo_url, rev="master"):
        self.repo_url = repo_url
        self.rev = rev


    def __eq__(self, other):
        return (self.repo_url == other.repo_url and self.rev == other.rev)


    def __hash__(self):
        return hash((self.repo_url, self.rev,))

    
    def __cmp__(self, other):
        """
        Head a is upstream of Head b -> a < b
        """
        def get_index(head):
            """
            A head with no url is considered out of tree. Any other head with a
            url is upstream of it.
            """
            if head.repo_url == RepoURL(None):
                return len(remotes)
            else:
                return remote_index[head]
        a = get_index(self)
        b = get_index(other)
        return cmp(a, b)


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
# linux-next is not a good reference because it gets rebased. If a commit is in
# linux-next, it comes from some other tree. Please tag the patch accordingly.
#
# Head(RepoURL(remote url), remote branch name)[]
# Note that "remote url" can be abbreviated if it starts with one of the usual
# kernel.org prefixes and "remote branch name" can be omitted if it is "master".
remotes = (
    Head(RepoURL("torvalds/linux.git")),
    Head(RepoURL("davem/net.git")),
    Head(RepoURL("davem/net-next.git")),
    Head(RepoURL("rdma/rdma.git"), "for-rc"),
    Head(RepoURL("rdma/rdma.git"), "for-next"),
    Head(RepoURL("dledford/rdma.git"), "k.o/for-next"),
    Head(RepoURL("jejb/scsi.git"), "for-next"),
    Head(RepoURL("bp/bp.git"), "for-next"),
    Head(RepoURL("tiwai/sound.git")),
    Head(RepoURL("git://linuxtv.org/media_tree.git")),
    Head(RepoURL("powerpc/linux.git"), "next"),
    Head(RepoURL("tip/tip.git")),
    Head(RepoURL("shli/md.git"), "for-next"),
    Head(RepoURL("dhowells/linux-fs.git"), "keys-uefi"),
    Head(RepoURL("git://git.infradead.org/nvme.git"), "nvme-4.15"),
    Head(RepoURL("tytso/ext4.git"), "dev"),
    Head(RepoURL("s390/linux.git"), "for-linus"),
    Head(RepoURL("tj/libata.git"), "for-next"),
    Head(RepoURL("https://github.com/kdave/btrfs-devel.git"), "misc-next"),
    Head(RepoURL("git://people.freedesktop.org/~airlied/linux"), "drm-next"),
    Head(RepoURL("gregkh/tty.git"), "tty-next"),
    Head(RepoURL("jj/linux-apparmor.git"), "v4.8-aa2.8-out-of-tree"),
    Head(RepoURL("pablo/nf.git")),
    Head(RepoURL("pablo/nf-next.git")),
    Head(RepoURL("horms/ipvs.git")),
    Head(RepoURL("horms/ipvs-next.git")),
    Head(RepoURL("klassert/ipsec.git")),
    Head(RepoURL("klassert/ipsec-next.git")),
)


remote_index = dict(zip(remotes, range(len(remotes))))
oot = Head(RepoURL(None), "out-of-tree patches")


class SortIndex(object):
    cache_version = 3
    version_match = re.compile("refs/tags/v(2\.6\.\d+|\d\.\d+)(-rc\d+)?$")


    def __init__(self, repo, skip_rebuild=False):
        self.repo = repo
        try:
            self.repo_heads = self.get_heads()
            self.history = self.get_history(skip_rebuild)
        except GSError as err:
            print("Error: %s" % (err,), file=sys.stderr)
            sys.exit(1)
        self.version_indexes = None


    def get_heads(self):
        """
        Returns
        repo_heads[Head]
            sha1
        """
        result = collections.OrderedDict()
        repo_remotes = []
        args = ("git", "config", "--get-regexp", "^remote\..+\.url$",)
        for line in subprocess.check_output(args,
                                            cwd=self.repo.path,
                                            env={}).splitlines():
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
                [(Head(RepoURL(None), "HEAD"),
                  str(self.repo.revparse_single("HEAD").id),)])

        return result


    def rebuild_history(self):
        """
        Returns
        history[Head][commit hash represented as string of 40 characters]
                index, an ordinal number such that
                commit a is an ancestor of commit b -> index(a) < index(b)
        """
        processed = []
        history = collections.OrderedDict()
        args = ["git", "log", "--topo-order", "--pretty=tformat:%H"]
        for head, rev in self.repo_heads.items():
            if head in history:
                raise GSException("head \"%s\" is not unique." % (head,))

            sp = subprocess.Popen(args + processed + [rev],
                                  cwd=self.repo.path,
                                  env={},
                                  stdout=subprocess.PIPE,
                                  stderr=subprocess.STDOUT)

            result = {}
            for l in sp.stdout:
                result[l.strip()] = len(result)
            # reverse indexes
            history[head] = {commit : len(result) - val for commit, val in
                             result.items()}

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
                (url, rev, sha1,
                 history[commit hash represented as string of 40 characters]
                    index (as described in get_history())
                 ,)

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


    def lookup(self, commit):
        for head, log in self.history.items():
            try:
                index = log[commit]
            except KeyError:
                continue
            else:
                return (head, index,)

        raise GSKeyError


    def sort(self, mapping):
        """
        Returns an OrderedDict
        result[Head][]
            sorted values from the mapping which are found in Head
        """
        result = collections.OrderedDict([(head, [],) for head in self.history])
        for commit in mapping.keys():
            try:
                head, index = self.lookup(commit)
            except GSKeyError:
                continue
            else:
                result[head].append((index, mapping.pop(commit),))

        for head, entries in result.items():
            entries.sort(key=operator.itemgetter(0))
            result[head] = [e[1] for e in entries]

        return result


    def describe(self, index):
        """
        index must come from the mainline head (remotes[0]).
        """
        if self.version_indexes is None:
            history = self.history[remotes[0]]
            # remove "refs/tags/"
            objects = [(self.repo.revparse_single(tag).get_object(), tag[10:],)
                       for tag in self.repo.listall_references()
                       if self.version_match.match(tag)]
            revs = [(history[str(obj.id)], tag,)
                    for obj, tag in objects
                    if obj.type == pygit2.GIT_OBJ_COMMIT]
            revs.sort(key=operator.itemgetter(0))
            self.version_indexes = zip(*revs)

        indexes, tags = self.version_indexes
        i = bisect.bisect_left(indexes, index)
        if i == len(tags):
            # not yet part of a tagged release
            m = re.search("v([0-9]+)\.([0-9]+)(|-rc([0-9]+))$", tags[-1])
            if m:
                # Post-release commit with no rc, it'll be rc1
                if m.group(3) == "":
                    nexttag = "v%s.%d-rc1" % (m.group(1), int(m.group(2)) + 1)
                else:
                    nexttag = "v%s.%d or v%s.%s-rc%d (next release)" % \
                              (m.group(1), int(m.group(2)), m.group(1),
                               m.group(2), int(m.group(4)) + 1)
            return nexttag
        else:
            return tags[i]


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

    print("".join([line
                   for entries in index.sort(lines).values()
                       for entry in entries
                           for line in entry
                  ]), end="")

    if len(lines) != 0:
        print("Error: the following entries were not found in the indexed heads:",
              file=sys.stderr)
        print("".join([line for line_list in lines.values() for line in
                       line_list]), end="")
        sys.exit(1)
