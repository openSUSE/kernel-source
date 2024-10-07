# -*- coding: utf-8 -*-

# Copyright (C) 2019 SUSE LLC
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

import sys

try:
    from pygit2 import *
    from pygit2 import __version__
    if 'GIT_OBJ_TAG' in dir() and 'GIT_OBJECT_TAG' not in dir():
        GIT_OBJECT_TAG = GIT_OBJ_TAG
        GIT_OBJECT_COMMIT = GIT_OBJ_COMMIT
    if 'enums' in dir():
        if hasattr(enums.ReferenceType, 'DIRECT'):
            GIT_REF_OID = enums.ReferenceType.DIRECT
    if __version__ < '1':
        import pathlib
        _old_init_repository = init_repository
        def _fix_init_repository(*args, **kwargs):
            args = [str(a) if isinstance(a, pathlib.PurePath) else a for a in args]
            return _old_init_repository(*args, **kwargs)
        init_repository = _fix_init_repository
except ImportError as err:
    print("Error: %s" % (err,), file=sys.stderr)
    print("Please install the \"pygit2\" python3 module. For more details, "
          "please refer to the \"Installation Requirements\" section of "
          "\"scripts/git_sort/README.md\".", file=sys.stderr)
    sys.exit(1)
