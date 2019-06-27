#!/usr/bin/env python3
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
except ImportError as err:
    print("Error: %s" % (err,), file=sys.stderr)
    print("Please install the \"pygit2\" python3 module. For more details, "
          "please refer to the \"Installation Requirements\" section of "
          "\"scripts/git_sort/README.md\".", file=sys.stderr)
    sys.exit(1)
