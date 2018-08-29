#!/usr/bin/python3
# -*- coding: utf-8 -*-

import io
import re
import sys

import exc


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


    def change(self, tag, value):
        """
        Changes the value of all instances of the tag.

        tag does not contain the terminal ": ". It is case insensitive.
        """
        if not self.f.writable():
            raise exc.KSException("Modification of read-only Patch")

        if len(self.get(tag)):
            self.modified = True
            start = "%s: " % (tag.lower(),)

            def change_value(line):
                if line.lower().startswith(start):
                    return "%s%s\n" % (line[:len(start)], value.strip(),)
                else:
                    return line

            self.head = [change_value(line) for line in self.head]
        else:
            raise KeyError("Tag \"%s\" not found" % (tag,))
