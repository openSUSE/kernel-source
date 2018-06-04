# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the
# Free Software Foundation; either version 2 of the License, or (at your
# option) any later version.  See http://www.gnu.org/copyleft/gpl.html for
# the full text of the license.

from .base import Bugzilla
from .rhbugzilla import RHBugzilla


# These are old compat classes. Nothing new should be added here,
# and these should not be altered

class Bugzilla3(Bugzilla): pass
class Bugzilla32(Bugzilla): pass
class Bugzilla34(Bugzilla): pass
class Bugzilla36(Bugzilla): pass
class Bugzilla4(Bugzilla): pass
class Bugzilla42(Bugzilla): pass
class Bugzilla44(Bugzilla): pass
class NovellBugzilla(Bugzilla): pass
class RHBugzilla3(RHBugzilla): pass
class RHBugzilla4(RHBugzilla): pass
