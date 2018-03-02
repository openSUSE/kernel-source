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
import types


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

        # an undocumented alias
        if url == "git://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux-2.6.git":
            url = "git://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git"

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
    Head(RepoURL("powerpc/linux.git"), "fixes"),
    Head(RepoURL("powerpc/linux.git"), "next"),
    Head(RepoURL("tip/tip.git")),
    Head(RepoURL("shli/md.git"), "for-next"),
    Head(RepoURL("dhowells/linux-fs.git"), "keys-uefi"),
    Head(RepoURL("git://git.infradead.org/nvme.git"), "nvme-4.15"),
    Head(RepoURL("git://git.infradead.org/nvme.git"), "nvme-4.16"),
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
    Head(RepoURL("mkp/scsi.git"), "4.15/scsi-fixes"),
    Head(RepoURL("mkp/scsi.git"), "4.16/scsi-fixes"),
    Head(RepoURL("mkp/scsi.git"), "4.17/scsi-queue"),
    Head(RepoURL("git://git.kernel.dk/linux-block.git"), "for-next"),
    Head(RepoURL("git://git.kernel.org/pub/scm/virt/kvm/kvm.git"), "queue"),
    Head(RepoURL("git://git.infradead.org/nvme.git"), "nvme-4.16-rc"),
    Head(RepoURL("powerpc/linux.git"), 'fixes'),
    Head(RepoURL("dhowells/linux-fs.git")),
)


remote_index = dict(zip(remotes, range(len(remotes))))
oot = Head(RepoURL(None), "out-of-tree patches")

remote_match = re.compile("remote\..+\.url")


def get_heads(repo):
    """
    Returns
    repo_heads[Head]
        sha1
    """
    result = collections.OrderedDict()
    repo_remotes = collections.OrderedDict([
        (RepoURL(repo.config[name]), ".".join(name.split(".")[1:-1]))
        for name in repo.config
        if remote_match.match(name)])

    for head in remotes:
        try:
            remote_name = repo_remotes[head.repo_url]
        except KeyError:
            continue

        rev = "remotes/%s/%s" % (remote_name, head.rev,)
        try:
            commit = repo.revparse_single(rev)
        except KeyError:
            raise GSError(
                "Could not read revision \"%s\". Perhaps you need to "
                "fetch from remote \"%s\", ie. `git fetch %s`." % (
                    rev, remote_name, remote_name,))
        result[head] = str(commit.id)

    if len(result) == 0 or result.keys()[0] != remotes[0]:
        # According to the urls in remotes, this is not a clone of linux.git
        # Sort according to commits reachable from the current head
        result = collections.OrderedDict(
            [(Head(RepoURL(None), "HEAD"),
              str(repo.revparse_single("HEAD").id),)])

    return result


def get_history(repo, repo_heads):
    """
    Returns
    history[Head][commit hash represented as string of 40 characters]
            index, an ordinal number such that
            commit a is an ancestor of commit b -> index(a) < index(b)
    """
    processed = []
    history = collections.OrderedDict()
    args = ["git", "log", "--topo-order", "--pretty=tformat:%H"]
    for head, rev in repo_heads.items():
        if head in history:
            raise GSException("head \"%s\" is not unique." % (head,))

        sp = subprocess.Popen(args + processed + [rev],
                              cwd=repo.path,
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


class CException(BaseException):
    pass


class CError(CException):
    pass


class CNeedsRebuild(CException):
    pass


class CAbsent(CNeedsRebuild):
    pass


class CKeyError(CNeedsRebuild):
    pass


class CUnsupported(CNeedsRebuild):
    pass


class CInconsistent(CNeedsRebuild):
    pass


class Cache(object):
    """
    cache
        version
        history[]
            (url, rev, sha1,
             history[commit hash represented as string of 40 characters]
                index (as described in get_history())
             ,)

    The cache is stored using basic types.
    """
    version = 3


    def __init__(self, write_enable=False):
        self.write_enable = write_enable
        self.closed = True
        try:
            cache_dir = os.environ["XDG_CACHE_HOME"]
        except KeyError:
            cache_dir = os.path.expanduser("~/.cache")
        cache_path = os.path.join(cache_dir, "git-sort")
        try:
            os.stat(cache_path)
        except OSError as e:
            if e.errno == 2:
                if write_enable:
                    if not os.path.isdir(cache_dir):
                        try:
                            os.makedirs(cache_dir)
                        except OSError as err:
                            raise CError("Could not create cache directory:\n" +
                                         str(err))
                else:
                    raise CAbsent
            else:
                raise

        flag_map = {False : "r", True : "n"}
        self.cache = shelve.open(cache_path, flag=flag_map[write_enable])
        self.closed = False
        if write_enable:
            self.cache["version"] = Cache.version


    def __del__(self):
        self.close()


    def __enter__(self):
        return self


    def __exit__(self, *args):
        self.close()


    def close(self):
        if not self.closed:
            self.cache.close()
        self.closed = True


    def __getitem__(self, key):
        """
        Supported keys:
            "version"
                int
            "history"
                OrderedDict((Head, sha1) : history)
        """
        if self.closed:
            raise ValueError

        if key == "version":
            try:
                return self.cache["version"]
            except KeyError:
                raise CKeyError
        elif key == "history":
            try:
                if self.cache["version"] != Cache.version:
                    raise CUnsupported
            except KeyError:
                raise CUnsupported

            try:
                cache_history = self.cache["history"]
            except KeyError:
                raise CInconsistent

            # This detailed check may be needed if an older git-sort (which
            # didn't set a cache version) modified the cache.
            if (not isinstance(cache_history, types.ListType) or
                len(cache_history) < 1 or 
                len(cache_history[0]) != 4 or
                not isinstance(cache_history[0][3], types.DictType)):
                raise CInconsistent

            return collections.OrderedDict([
                (
                    (Head(RepoURL(e[0]), e[1]), e[2],),
                    e[3],
                ) for e in cache_history])
        else:
            raise KeyError


    def __setitem__(self, key, value):
        """
        Supported keys:
            "history"
                OrderedDict((Head, sha1) : history)
        """
        if self.closed or not self.write_enable:
            raise ValueError

        if key == "history":
            self.cache["history"] = [(
                repr(desc[0].repo_url), desc[0].rev, desc[1], log,
            ) for desc, log in value.items()]
        else:
            raise KeyError


class SortIndex(object):
    version_match = re.compile("refs/tags/v(2\.6\.\d+|\d\.\d+)(-rc\d+)?$")


    def __init__(self, repo):
        self.repo = repo
        needs_rebuild = False
        try:
            with Cache() as cache:
                try:
                    history = cache["history"]
                except CNeedsRebuild:
                    needs_rebuild = True
        except CAbsent:
            needs_rebuild = True
        except CError as err:
            print("Error: %s" % (err,), file=sys.stderr)
            sys.exit(1)

        try:
            repo_heads = get_heads(repo)
        except GSError as err:
            print("Error: %s" % (err,), file=sys.stderr)
            sys.exit(1)

        if needs_rebuild or history.keys() != repo_heads.items():
            try:
                history = get_history(repo, repo_heads)
            except GSError as err:
                print("Error: %s" % (err,), file=sys.stderr)
                sys.exit(1)
            try:
                with Cache(write_enable=True) as cache:
                    cache["history"] = collections.OrderedDict(
                        [((head, repo_heads[head],), log,)
                         for head, log in history.items()])
            except CError as err:
                print("Error: %s" % (err,), file=sys.stderr)
                sys.exit(1)
            self.history = history
        else:
            # no more need for the head sha1
            self.history = collections.OrderedDict(
                    [(key[0], log,) for key, log in history.items()])
        self.version_indexes = None
        self.repo_heads = repo_heads


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
            # Remove "refs/tags/"
            # Mainline release tags are annotated tag objects attached to a
            # commit object; do not consider other kinds of tags.
            objects = [(obj_tag.get_object(), tag,)
                       for obj_tag, tag in [
                           (self.repo.revparse_single(tag), tag[10:],)
                           for tag in self.repo.listall_references()
                           if self.version_match.match(tag)
                       ] if obj_tag.type == pygit2.GIT_OBJ_TAG]
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

    if args.dump_heads:
        needs_rebuild = False
        try:
            with Cache() as cache:
                try:
                    print("Cached heads (version %d):" % cache["version"])
                except CKeyError:
                    print("No usable cache")
                    needs_rebuild = True
                else:
                    try:
                        history = cache["history"]
                    except CUnsupported:
                        print("Unsupported cache version")
                        needs_rebuild = True
                    except CInconsistent:
                        print("Inconsistent cache content")
                        needs_rebuild = True
                    else:
                        pprint.pprint(history.keys())
        except CAbsent:
            print("No usable cache")
            needs_rebuild = True
        except CError as err:
            print("Error: %s" % (err,), file=sys.stderr)
            sys.exit(1)

        try:
            repo_heads = get_heads(repo)
        except GSError as err:
            print("Error: %s" % (err,), file=sys.stderr)
            sys.exit(1)
        if not needs_rebuild and history.keys() != repo_heads.items():
            needs_rebuild = True
        print("Current heads (version %d):" % Cache.version)
        pprint.pprint(repo_heads.items())
        if needs_rebuild:
            action = "Will"
        else:
            action = "Will not"
        print("%s rebuild history" % (action,))
        sys.exit(0)

    index = SortIndex(repo)
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
