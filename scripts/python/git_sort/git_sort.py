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

import bisect
import collections
import dbm
import functools
import operator
import os
import re
import shelve
import subprocess
import sys
from pathlib import Path
from . import pygit2_wrapper as pygit2

try:
    import yaml
except ImportError as err:
    print("Error: %s" % (err,), file=sys.stderr)
    print("Please install the \"PyYAML\" python3 module. For more details, "
          "please refer to the \"Installation Requirements\" section of "
          "\"scripts/git_sort/README.md\".", file=sys.stderr)
    sys.exit(1)


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
            "ssh://git@gitolite.kernel.org/pub/scm/linux/kernel/git/",
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


    def _is_valid_operand(self, other):
        return hasattr(other, "url")


    def __eq__(self, other):
        if not self._is_valid_operand(other):
            return NotImplemented
        return self.url == other.url


    def __ne__(self, other):
        if not self._is_valid_operand(other):
            return NotImplemented
        return self.url != other.url


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


@functools.total_ordering
class Head(object):
    def __init__(self, repo_url, rev="master"):
        self.repo_url = repo_url
        self.rev = rev


    def _is_valid_operand(self, other):
        return hasattr(other, "repo_url") and hasattr(other, "rev")


    def _get_index(self):
        """
        A head with no url is considered out of tree. Any other head with a
        url is upstream of it.
        """
        if self.repo_url == RepoURL(None):
            return len(remotes)
        else:
            return remote_index[self]


    def __eq__(self, other):
        if not self._is_valid_operand(other):
            return NotImplemented
        return (self.repo_url == other.repo_url and self.rev == other.rev)


    def __lt__(self, other):
        if not self._is_valid_operand(other):
            return NotImplemented
        return self._get_index() < other._get_index()


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


remotes = ()

file = os.environ.get('GIT_SORT_REPOSITORIES')
if file:
    file = Path(file)
else:
    this_file = Path(__file__)
    file = this_file.parent / (this_file.stem + '.yaml')
with file.open() as fd:
    remotes = yaml.safe_load(fd)

def construct_head(x):
    return Head(RepoURL(x[0]), *x[1:])

remotes = tuple(map(construct_head, remotes))
remote_index = dict(zip(remotes, list(range(len(remotes)))))
oot = Head(RepoURL(None), "out-of-tree patches")


def get_heads(repo):
    """
    Returns
    repo_heads[Head]
        sha1
    """
    result = collections.OrderedDict()
    repo_remotes = collections.OrderedDict(
        ((RepoURL(remote.url), remote,) for remote in repo.remotes))

    for head in remotes:
        if head in result:
            raise GSException("head \"%s\" is not unique." % (head,))

        try:
            remote = repo_remotes[head.repo_url]
        except KeyError:
            continue

        lhs = "refs/heads/%s" % (head.rev,)
        rhs = None
        nb = len(remote.fetch_refspecs)
        if nb == 0:
            # `git clone --bare` case
            rhs = lhs
        else:
            for i in range(nb):
                r = remote.get_refspec(i)
                if r.src_matches(lhs):
                    rhs = r.transform(lhs)
                    break
        if rhs is None:
            raise GSError("No matching fetch refspec for head \"%s\"." %
                          (head,))
        try:
            commit = repo.revparse_single(rhs)
        except KeyError:
            raise GSError("Could not read revision \"%s\". Perhaps you need "
                          "to fetch from remote \"%s\"" % (rhs, remote.name,))
        result[head] = str(commit.id)

    if len(result) == 0 or list(result.keys())[0] != remotes[0]:
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
        sp = subprocess.Popen(args + processed + [rev],
                              cwd=repo.path,
                              env={},
                              stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT)

        result = {}
        for l in sp.stdout:
            result[l.decode().strip()] = len(result)
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

        if write_enable:
            # In case there is already a database file of an unsupported format,
            # one would hope that with flag="n" a new database would be created
            # to overwrite the current one. Alas, that is not the case... :'(
            try:
                os.unlink(cache_path)
            except OSError as e:
                if e.errno != 2:
                    raise

        flag_map = {False : "r", True : "n"}
        try:
            self.cache = shelve.open(cache_path, flag=flag_map[write_enable])
        except dbm.error:
            raise CUnsupported
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

        try:
            version = self.cache["version"]
        except KeyError:
            key_error = True
        except ValueError as err:
            raise CUnsupported(str(err))
        else:
            key_error = False

        if key == "version":
            if key_error:
                raise CKeyError
            else:
                return version
        elif key == "history":
            if key_error or version != Cache.version:
                raise CUnsupported

            try:
                cache_history = self.cache["history"]
            except KeyError:
                raise CInconsistent

            # This detailed check may be needed if an older git-sort (which
            # didn't set a cache version) modified the cache.
            if (not isinstance(cache_history, list) or
                len(cache_history) < 1 or
                len(cache_history[0]) != 4 or
                not isinstance(cache_history[0][3], dict)):
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


@functools.total_ordering
class IndexedCommit(object):
    def __init__(self, head, index):
        self.head = head
        self.index = index


    def _is_valid_operand(self, other):
        return hasattr(other, "head") and hasattr(other, "index")


    def __eq__(self, other):
        if not self._is_valid_operand(other):
            return NotImplemented
        return (self.head == other.head and self.index == other.index)


    def __lt__(self, other):
        if not self._is_valid_operand(other):
            return NotImplemented
        if self.head == other.head:
            return self.index < other.index
        else:
            return self.head < other.head


    def __hash__(self):
        return hash((self.head, self.index,))


    def __repr__(self):
        return "%s %d" % (repr(self.head), self.index,)


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
        except CNeedsRebuild:
            needs_rebuild = True
        except CError as err:
            print("Error: %s" % (err,), file=sys.stderr)
            sys.exit(1)

        try:
            repo_heads = get_heads(repo)
        except GSError as err:
            print("Error: %s" % (err,), file=sys.stderr)
            sys.exit(1)

        if needs_rebuild or list(history.keys()) != list(repo_heads.items()):
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
                return IndexedCommit(head, index)

        raise GSKeyError


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
                       ] if obj_tag.type == pygit2.GIT_OBJECT_TAG]
            revs = [(history[str(obj.id)], tag,)
                    for obj, tag in objects
                    if obj.type == pygit2.GIT_OBJECT_COMMIT]
            revs.sort(key=operator.itemgetter(0))
            self.version_indexes = list(zip(*revs))

        if not self.version_indexes:
            raise GSError("Cannot describe commit, did not find any mainline "
                          "release tags in repository.")

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
