# python-bugzilla - a Python interface to bugzilla using xmlrpclib.
#
# Copyright (C) 2007, 2008 Red Hat Inc.
# Author: Will Woods <wwoods@redhat.com>
#
# This work is licensed under the GNU GPLv2 or later.
# See the COPYING file in the top-level directory.

from .apiversion import version, __version__
from .base import Bugzilla
from .exceptions import BugzillaError
from .oldclasses import (Bugzilla3, Bugzilla32, Bugzilla34, Bugzilla36,
        Bugzilla4, Bugzilla42, Bugzilla44,
        NovellBugzilla, RHBugzilla, RHBugzilla3, RHBugzilla4)


# This is the public API. If you are explicitly instantiating any other
# class, using some function, or poking into internal files, don't complain
# if things break on you.
__all__ = [
    "Bugzilla3", "Bugzilla32", "Bugzilla34", "Bugzilla36",
    "Bugzilla4", "Bugzilla42", "Bugzilla44",
    "NovellBugzilla",
    "RHBugzilla3", "RHBugzilla4", "RHBugzilla",
    'BugzillaError',
    'Bugzilla', "version",
]


# Clear all other locals() from the public API
for __sym in locals().copy():
    if __sym.startswith("__") or __sym in __all__:
        continue
    locals().pop(__sym)
locals().pop("__sym")
