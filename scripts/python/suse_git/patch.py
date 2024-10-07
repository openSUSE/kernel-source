# vim: sw=4 ts=4 et si:

from enum import Enum
import io
import re
import sys

import suse_git.exc as exc
import suse_git.util as util

class ValidationError(Exception):
    pass

class PatchException(Exception):
    def __init__(self, errors):
        Exception.__init__(self, "Validation Error")
        self._errors = errors

    def errors(self, error=None):
        count = 0
        if error is None:
            return len(self._errors)
        for err in self._errors:
            if isinstance(err, error):
                count += 1
        return count

    def __str__(self):
        return "\n".join("** %s" % str(x) for x in self._errors)

    def __repr__(self):
        ret = "%d errors:\n" % len(self._errors)
        ret += "\n".join(self._errors)
        return ret

    def error_message(self, fn):
        ret = "ERROR: Problems encountered in "
        if fn:
            ret += "`%s'\n" % fn
        else:
            ret += "input\n"

        ret += str(self)

        return ret

class PatchChecker:
    def __init__(self):
        pass

    def do_patch(self):
        pass

class Patch(object):
    # This pattern was copied from quilt/scripts/patchfns.in:patch_header() in
    # the quilt sources
    break_matcher = re.compile(b"(---|\*\*\*|Index:)[ \t][^ \t]|^diff -")

    def __init__(self, f):
        assert(f.tell() == 0)
        assert(isinstance(f, io.BufferedIOBase)) # binary (bytes) io object

        self.modified = False
        self.f = f
        self.head = []
        self.body = b""
        for line in f:
            if self.break_matcher.match(line):
                self.body = line
                break
            self.head.append(line.decode())


    def __del__(self):
        self.writeback()


    def __enter__(self):
        return self


    def __exit__(self, *args):
        self.writeback()


    def writeback(self):
        if not self.modified:
            return

        self.body = self.body + self.f.read()
        self.f.seek(0)
        self.f.writelines([line.encode() for line in self.head])
        self.f.write(self.body)
        self.f.truncate()

        self.modified = False


    def get(self, tag):
        """
        tag does not contain the terminal ": ". It is case insensitive.

        Returns a list with the value for each instance of the tag.
        """
        start = "%s: " % (tag.lower(),)
        return [line[len(start):].strip()
                for line in self.head
                if line.lower().startswith(start)]

    def get_list_normalized(self, tag):
        """
        Treat tag value (in all instances) as a list of tokens delimited by
        whitespace or commas.

        Returns normalized set of tokens.
        """
        tokens = " ".join(self.get(tag)).replace(",", " ").split()
        return References(tokens)

    def remove(self, tag):
        """
        Removes all instances of the tag.

        tag does not contain the terminal ": ". It is case insensitive.
        """
        if not self.f.writable():
            raise exc.KSException("Modification of read-only Patch")

        if len(self.get(tag)):
            self.modified = True
            start = "%s: " % (tag.lower(),)
            self.head = [line
                         for line in self.head
                         if not line.lower().startswith(start)]


    class ChangeMode(Enum):
        EACH = 1        # change value of each instance
        ALL_WITH_ONE = 2# change value of first instance, drop other

    def change(self, tag, value, mode=ChangeMode.EACH):
        """
        Changes the value of instances of the tag based on mode.

        tag does not contain the terminal ": ". It is case insensitive.
        """
        if not self.f.writable():
            raise exc.KSException("Modification of read-only Patch")

        if len(self.get(tag)):
            self.modified = True
            start = "%s: " % (tag.lower(),)

            replaced = False
            new_head = []
            for line in self.head:
                if not line.lower().startswith(start):
                    new_head.append(line)
                    continue
                if replaced and mode == Patch.ChangeMode.ALL_WITH_ONE:
                    continue
                new_head.append("%s%s\n" % (line[:len(start)], value.strip(),))
                replaced = True
            self.head = new_head
        else:
            raise KeyError("Tag \"%s\" not found" % (tag,))

class References(util.OrderedSet):
    """
    Class represents set of patch references, it is case insensitive and
    order-preserving to avoid unnecessary changes touching patches.
    """
    def __init__(self, iterable=None):
        self.__ci_set = set()
        super().__init__(iterable)

    def add(self, key):
        if key not in self:
            self.__ci_set.add(References._canon(key))
            super().add(key)

    def __contains__(self, key):
        return References._canon(key) in self.__ci_set

    def __eq__(self, other):
        if isinstance(other, References):
            return self.__ci_set == other.__ci_set
        return super().__eq__(other)

    def _canon(val):
        return val.lower()
