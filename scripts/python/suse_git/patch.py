#!/usr/bin/env python
# vim: sw=4 ts=4 et si:

import sys

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

    def print_errors(self, errors, fn="stdin"):
        ret = 0
        if errors:
            print >>sys.stderr, "ERROR: Problems encountered in",
            if fn:
                print >>sys.stderr, "`%s'" % fn
            else:
                print >>sys.stderr, "input"
        for error in errors:
            print >>sys.stderr, "** %s" % error
            ret = 1

        return ret
