# This work is licensed under the GNU GPLv2 or later.
# See the COPYING file in the top-level directory.

from .base import Bugzilla

# These are old compat classes. Nothing new should be added here,
# and these should not be altered


class Bugzilla3(Bugzilla):
    pass


class Bugzilla32(Bugzilla):
    pass


class Bugzilla34(Bugzilla):
    pass


class Bugzilla36(Bugzilla):
    pass


class Bugzilla4(Bugzilla):
    pass


class Bugzilla42(Bugzilla):
    pass


class Bugzilla44(Bugzilla):
    pass


class NovellBugzilla(Bugzilla):
    pass


class RHBugzilla(Bugzilla):
    """
    Helper class for historical bugzilla.redhat.com back compat

    Historically this class used many more non-upstream methods, but
    in 2012 RH started dropping most of its custom bits. By that time,
    upstream BZ had most of the important functionality.

    Much of the remaining code here is just trying to keep things operating
    in python-bugzilla back compatible manner.

    This class was written using bugzilla.redhat.com's API docs:
    https://bugzilla.redhat.com/docs/en/html/api/
    """
    _is_redhat_bugzilla = True


class RHBugzilla3(RHBugzilla):
    pass


class RHBugzilla4(RHBugzilla):
    pass
