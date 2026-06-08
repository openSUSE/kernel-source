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

import subprocess
import tempfile
import pathlib
import shelve
import shutil
import sys
import os

# fixups for python 3.6, works flawlessly in python 3.11
if sys.version_info.minor < 11:  # SLE15
    _shelve_open = shelve.open
    def _fix_shelve(*args, **kwargs):
        args = [str(a) if isinstance(a, pathlib.PurePath) else a for a in args]
        return _shelve_open(*args, **kwargs)

    shelve.open = _fix_shelve

    if sys.version_info.minor >= 6:
        class _FixPopen(subprocess.Popen):
            def __init__(self, *args, **kwargs):
                args = [str(a) if isinstance(a, pathlib.PurePath) else a for a in args]
                super().__init__(*args, **kwargs)

    else:  # SLE12
        class _FixPopen(subprocess.Popen):
            def __init__(self, *args, **kwargs):
                args = [str(a) if isinstance(a, pathlib.PurePath) else a if not isinstance(a, list) else [str(elt) if isinstance(elt, pathlib.PurePath) else elt for elt in a ] for a in args]
                new_kwargs = {}
                for key in kwargs:
                    value = kwargs[key]
                    new_kwargs[key] = str(value) if isinstance(value, pathlib.PurePath) else value
                super().__init__(*args, **new_kwargs)

        def _write_bytes(self, data):
            with self.open('wb') as f: f.write(data)

        pathlib.PurePath.write_bytes = _write_bytes

        def _read_bytes(self):
            with self.open('rb') as f: return f.read()

        pathlib.PurePath.read_bytes = _read_bytes

        def _write_text(self, text):
            with self.open('w') as f: f.write(text)

        pathlib.PurePath.write_text = _write_text

        def _read_text(self):
            with self.open() as f: return f.read()

        pathlib.PurePath.read_text = _read_text

        _os_stat = os.stat
        def _fix_stat(*args, **kwargs):
            args = [str(a) if isinstance(a, pathlib.PurePath) else a for a in args]
            return _os_stat(*args, **kwargs)

        os.stat = _fix_stat

        _shutil_copy = shutil.copy
        def _fix_copy(*args, **kwargs):
            args = [str(a) if isinstance(a, pathlib.PurePath) else a for a in args]
            return _shutil_copy(*args, **kwargs)

        shutil.copy = _fix_copy

        _shutil_rmtree = shutil.rmtree
        def _fix_rmtree(*args, **kwargs):
            args = [str(a) if isinstance(a, pathlib.PurePath) else a for a in args]
            return _shutil_rmtree(*args, **kwargs)

        shutil.rmtree = _fix_rmtree

        _tempfile_mkstemp = tempfile.mkstemp
        def _fix_mkstemp(*args, **kwargs):
            args = [str(a) if isinstance(a, pathlib.PurePath) else a for a in args]
            new_kwargs = {}
            for key in kwargs:
                value = kwargs[key]
                new_kwargs[key] = str(value) if isinstance(value, pathlib.PurePath) else value
            return _tempfile_mkstemp(*args, **new_kwargs)

        tempfile.mkstemp = _fix_mkstemp

    subprocess.Popen = _FixPopen
