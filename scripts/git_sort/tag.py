#!/usr/bin/python
# -*- coding: utf-8 -*-

import sys


class Patch(object):
    def __init__(self, name=None, content=None):
        self.name = None
        if name:
            self.name = name
            self.head = open(name).readlines()
            self.modified = False
            self.closed = False
        elif content:
            self.head = ["%s\n" % (l,) for l in content.splitlines()]
            self.closed = True
        else:
            self.head = sys.stdin.readlines()
            self.modified = False
            self.closed = False

        self.body = []
        for i in range(len(self.head)):
            # These patterns were copied from
            # quilt/scripts/patchfns.in:patch_header()
            # in the quilt sources
            if self.head[i].startswith(("---", "***", "Index:", "diff -",)):
                self.body = self.head[i:]
                self.head = self.head[:i]
                break


    def __del__(self):
        self.close()


    def __enter__(self):
        return self


    def __exit__(self, *args):
        self.close()


    def close(self):
        if not self.closed:
            self.writeback()
        self.closed = True


    def writeback(self):
        if self.name:
            if self.modified:
                with open(self.name, mode="w") as output:
                    output.writelines(self.head)
                    output.writelines(self.body)
        else:
            sys.stdout.writelines(self.head)
            sys.stdout.writelines(self.body)
            sys.stdout.flush()


    def get(self, tag):
        """
        tag does not contain the terminal ": ". It is case insensitive.

        Returns a list with the value for each instance of the tag.
        """
        start = "%s: " % (tag.lower(),)
        return [line[len(start):-1].strip() for line in self.head
                if line.lower().startswith(start)]


    def remove(self, tag):
        """
        Removes all instances of the tag.

        tag does not contain the terminal ": ". It is case insensitive.
        """
        if self.closed:
            raise ValueError("Modification of closed Patch")

        if len(self.get(tag)):
            self.modified = True
            start = "%s: " % (tag.lower(),)
            self.head = [line for line in self.head
                         if not line.lower().startswith(start)]


    def change(self, tag, value):
        """
        Changes the value of all instances of the tag.

        tag does not contain the terminal ": ". It is case insensitive.
        """
        if self.closed:
            raise ValueError("Modification of closed Patch")

        if len(self.get(tag)):
            self.modified = True
            start = "%s: " % (tag.lower(),)

            def change_value(line):
                if line.lower().startswith(start):
                    return "%s%s\n" % (line[:len(start)], value.strip(),)
                else:
                    return line

            self.head = map(change_value, self.head)
        else:
            raise KeyError("Tag \"%s\" not found" % (tag,))
