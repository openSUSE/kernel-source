# base.py - the base classes etc. for a Python interface to bugzilla
#
# Copyright (C) 2007, 2008, 2009, 2010 Red Hat Inc.
# Author: Will Woods <wwoods@redhat.com>
#
# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the
# Free Software Foundation; either version 2 of the License, or (at your
# option) any later version.  See http://www.gnu.org/copyleft/gpl.html for
# the full text of the license.

from __future__ import unicode_literals
import locale
from logging import getLogger
import sys

log = getLogger(__name__)


class Bug(object):
    '''A container object for a bug report. Requires a Bugzilla instance -
    every Bug is on a Bugzilla, obviously.
    Optional keyword args:
        dict=DICT   - populate attributes with the result of a getBug() call
        bug_id=ID   - if dict does not contain bug_id, this is required before
                      you can read any attributes or make modifications to this
                      bug.
    '''
    def __init__(self, bugzilla, bug_id=None, dict=None, autorefresh=False):
        # pylint: disable=redefined-builtin
        # API had pre-existing issue that we can't change ('dict' usage)

        self.bugzilla = bugzilla
        self._bug_fields = []
        self.autorefresh = autorefresh

        if not dict:
            dict = {}
        if bug_id:
            dict["id"] = bug_id

        log.debug("Bug(%s)", sorted(dict.keys()))
        self._update_dict(dict)

        self.weburl = bugzilla.url.replace('xmlrpc.cgi',
                                           'show_bug.cgi?id=%i' % self.bug_id)

    def __str__(self):
        '''Return a simple string representation of this bug

        This is available only for compatibility. Using 'str(bug)' and
        'print(bug)' is not recommended because of potential encoding issues.
        Please use unicode(bug) where possible.
        '''
        if sys.version_info[0] >= 3:
            return self.__unicode__()
        else:
            return self.__unicode__().encode(
                locale.getpreferredencoding(), 'replace')

    def __unicode__(self):
        '''Return a simple unicode string representation of this bug'''
        return "#%-6s %-10s - %s - %s" % (self.bug_id, self.bug_status,
                                          self.assigned_to, self.summary)

    def __repr__(self):
        return '<Bug #%i on %s at %#x>' % (self.bug_id, self.bugzilla.url,
                                           id(self))

    def __getattr__(self, name):
        refreshed = False
        while True:
            if refreshed and name in self.__dict__:
                # If name was in __dict__ to begin with, __getattr__ would
                # have never been called.
                return self.__dict__[name]

            # pylint: disable=protected-access
            aliases = self.bugzilla._get_bug_aliases()
            # pylint: enable=protected-access

            for newname, oldname in aliases:
                if name == oldname and newname in self.__dict__:
                    return self.__dict__[newname]

            # Doing dir(bugobj) does getattr __members__/__methods__,
            # don't refresh for those
            if name.startswith("__") and name.endswith("__"):
                break

            if refreshed or not self.autorefresh:
                break

            log.info("Bug %i missing attribute '%s' - doing implicit "
                "refresh(). This will be slow, if you want to avoid "
                "this, properly use query/getbug include_fields, and "
                "set bugzilla.bug_autorefresh = False to force failure.",
                self.bug_id, name)

            # We pass the attribute name to getbug, since for something like
            # 'attachments' which downloads lots of data we really want the
            # user to opt in.
            self.refresh(extra_fields=[name])
            refreshed = True

        msg = ("Bug object has no attribute '%s'." % name)
        if not self.autorefresh:
            msg += ("\nIf '%s' is a bugzilla attribute, it may not have "
                    "been cached when the bug was fetched. You may want "
                    "to adjust your include_fields for getbug/query." % name)
        raise AttributeError(msg)

    def refresh(self, include_fields=None, exclude_fields=None,
        extra_fields=None):
        '''
        Refresh the bug with the latest data from bugzilla
        '''
        # pylint: disable=protected-access
        r = self.bugzilla._getbug(self.bug_id,
            include_fields=include_fields, exclude_fields=exclude_fields,
            extra_fields=self._bug_fields + (extra_fields or []))
        # pylint: enable=protected-access
        self._update_dict(r)
    reload = refresh

    def _update_dict(self, newdict):
        '''
        Update internal dictionary, in a way that ensures no duplicate
        entries are stored WRT field aliases
        '''
        if self.bugzilla:
            self.bugzilla.post_translation({}, newdict)

            # pylint: disable=protected-access
            aliases = self.bugzilla._get_bug_aliases()
            # pylint: enable=protected-access

            for newname, oldname in aliases:
                if oldname not in newdict:
                    continue

                if newname not in newdict:
                    newdict[newname] = newdict[oldname]
                elif newdict[newname] != newdict[oldname]:
                    log.debug("Update dict contained differing alias values "
                              "d[%s]=%s and d[%s]=%s , dropping the value "
                              "d[%s]", newname, newdict[newname], oldname,
                            newdict[oldname], oldname)
                del(newdict[oldname])

        for key in newdict.keys():
            if key not in self._bug_fields:
                self._bug_fields.append(key)
        self.__dict__.update(newdict)

        if 'id' not in self.__dict__ and 'bug_id' not in self.__dict__:
            raise TypeError("Bug object needs a bug_id")


    ##################
    # pickle helpers #
    ##################

    def __getstate__(self):
        ret = {}
        for key in self._bug_fields:
            ret[key] = self.__dict__[key]
        return ret

    def __setstate__(self, vals):
        self._bug_fields = []
        self.bugzilla = None
        self._update_dict(vals)


    #####################
    # Modify bug status #
    #####################

    def setstatus(self, status, comment=None, private=False):
        '''
        Update the status for this bug report.
        Commonly-used values are ASSIGNED, MODIFIED, and NEEDINFO.

        To change bugs to RESOLVED, use .close() instead.
        '''
        # Note: fedora bodhi uses this function
        vals = self.bugzilla.build_update(status=status,
                                          comment=comment,
                                          comment_private=private)
        log.debug("setstatus: update=%s", vals)

        return self.bugzilla.update_bugs(self.bug_id, vals)

    def close(self, resolution, dupeid=None, fixedin=None,
              comment=None, isprivate=False):
        '''Close this bug.
        Valid values for resolution are in bz.querydefaults['resolution_list']
        For bugzilla.redhat.com that's:
        ['NOTABUG', 'WONTFIX', 'DEFERRED', 'WORKSFORME', 'CURRENTRELEASE',
         'RAWHIDE', 'ERRATA', 'DUPLICATE', 'UPSTREAM', 'NEXTRELEASE',
         'CANTFIX', 'INSUFFICIENT_DATA']
        If using DUPLICATE, you need to set dupeid to the ID of the other bug.
        If using WORKSFORME/CURRENTRELEASE/RAWHIDE/ERRATA/UPSTREAM/NEXTRELEASE
          you can (and should) set 'new_fixed_in' to a string representing the
          version that fixes the bug.
        You can optionally add a comment while closing the bug. Set 'isprivate'
          to True if you want that comment to be private.
        '''
        # Note: fedora bodhi uses this function
        vals = self.bugzilla.build_update(comment=comment,
                                          comment_private=isprivate,
                                          resolution=resolution,
                                          dupe_of=dupeid,
                                          fixed_in=fixedin,
                                          status="RESOLVED")
        log.debug("close: update=%s", vals)

        return self.bugzilla.update_bugs(self.bug_id, vals)


    #####################
    # Modify bug emails #
    #####################

    def setassignee(self, assigned_to=None,
                    qa_contact=None, comment=None):
        '''
        Set any of the assigned_to or qa_contact fields to a new
        bugzilla account, with an optional comment, e.g.
        setassignee(assigned_to='wwoods@redhat.com')
        setassignee(qa_contact='wwoods@redhat.com', comment='wwoods QA ftw')

        You must set at least one of the two assignee fields, or this method
        will throw a ValueError.

        Returns [bug_id, mailresults].
        '''
        if not (assigned_to or qa_contact):
            raise ValueError("You must set one of assigned_to "
                             " or qa_contact")

        vals = self.bugzilla.build_update(assigned_to=assigned_to,
                                          qa_contact=qa_contact,
                                          comment=comment)
        log.debug("setassignee: update=%s", vals)

        return self.bugzilla.update_bugs(self.bug_id, vals)

    def addcc(self, cclist, comment=None):
        '''
        Adds the given email addresses to the CC list for this bug.
        cclist: list of email addresses (strings)
        comment: optional comment to add to the bug
        '''
        vals = self.bugzilla.build_update(comment=comment,
                                          cc_add=cclist)
        log.debug("addcc: update=%s", vals)

        return self.bugzilla.update_bugs(self.bug_id, vals)

    def deletecc(self, cclist, comment=None):
        '''
        Removes the given email addresses from the CC list for this bug.
        '''
        vals = self.bugzilla.build_update(comment=comment,
                                          cc_remove=cclist)
        log.debug("deletecc: update=%s", vals)

        return self.bugzilla.update_bugs(self.bug_id, vals)


    ####################
    # comment handling #
    ####################

    def addcomment(self, comment, private=False):
        '''
        Add the given comment to this bug. Set private to True to mark this
        comment as private.
        '''
        # Note: fedora bodhi uses this function
        vals = self.bugzilla.build_update(comment=comment,
                                          comment_private=private)
        log.debug("addcomment: update=%s", vals)

        return self.bugzilla.update_bugs(self.bug_id, vals)

    def getcomments(self):
        '''
        Returns an array of comment dictionaries for this bug
        '''
        comment_list = self.bugzilla.get_comments([self.bug_id])
        return comment_list['bugs'][str(self.bug_id)]['comments']


    #####################
    # Get/Set bug flags #
    #####################

    def get_flag_type(self, name):
        """
        Return flag_type information for a specific flag

        Older RHBugzilla returned a lot more info here, but it was
        non-upstream and is now gone.
        """
        for t in self.flags:
            if t['name'] == name:
                return t
        return None

    def get_flags(self, name):
        """
        Return flag value information for a specific flag
        """
        ft = self.get_flag_type(name)
        if not ft:
            return None

        return [ft]

    def get_flag_status(self, name):
        """
        Return a flag 'status' field

        This method works only for simple flags that have only a 'status' field
        with no "requestee" info, and no multiple values. For more complex
        flags, use get_flags() to get extended flag value information.
        """
        f = self.get_flags(name)
        if not f:
            return None

        # This method works only for simple flags that have only one
        # value set.
        assert len(f) <= 1

        return f[0]['status']

    def updateflags(self, flags):
        """
        Thin wrapper around build_update(flags=X). This only handles simple
        status changes, anything like needinfo requestee needs to call
        build_update + update_bugs directly

        :param flags: Dictionary of the form {"flagname": "status"}, example
            {"needinfo": "?", "devel_ack": "+"}
        """
        flaglist = []
        for key, value in flags.items():
            flaglist.append({"name": key, "status": value})
        return self.bugzilla.update_bugs([self.bug_id],
            self.bugzilla.build_update(flags=flaglist))


    ########################
    # Experimental methods #
    ########################

    def get_attachments(self, include_fields=None, exclude_fields=None):
        """
        Helper call to Bugzilla.get_attachments. If you want to fetch
        specific attachment IDs, use that function instead
        """
        if "attachments" in self.__dict__:
            return self.attachments

        data = self.bugzilla.get_attachments([self.bug_id], None,
                include_fields, exclude_fields)
        return data["bugs"][str(self.bug_id)]

    def get_attachment_ids(self):
        """
        Helper function to return only the attachment IDs for this bug
        """
        return [a["id"] for a in self.get_attachments(exclude_fields=["data"])]

    def get_history_raw(self):
        '''
        Experimental. Get the history of changes for this bug.
        '''
        return self.bugzilla.bugs_history_raw([self.bug_id])


class User(object):
    '''Container object for a bugzilla User.

    :arg bugzilla: Bugzilla instance that this User belongs to.
    Rest of the params come straight from User.get()
    '''
    def __init__(self, bugzilla, **kwargs):
        self.bugzilla = bugzilla
        self.__userid = kwargs.get('id')
        self.__name = kwargs.get('name')

        self.__email = kwargs.get('email', self.__name)
        self.__can_login = kwargs.get('can_login', False)

        self.real_name = kwargs.get('real_name', None)
        self.password = None

        self.groups = kwargs.get('groups', {})
        self.groupnames = []
        for g in self.groups:
            if "name" in g:
                self.groupnames.append(g["name"])
        self.groupnames.sort()


    ########################
    # Read-only attributes #
    ########################

    # We make these properties so that the user cannot set them.  They are
    # unaffected by the update() method so it would be misleading to let them
    # be changed.
    @property
    def userid(self):
        return self.__userid

    @property
    def email(self):
        return self.__email

    @property
    def can_login(self):
        return self.__can_login

    # name is a key in some methods.  Mark it dirty when we change it #
    @property
    def name(self):
        return self.__name

    def refresh(self):
        """
        Update User object with latest info from bugzilla
        """
        newuser = self.bugzilla.getuser(self.email)
        self.__dict__.update(newuser.__dict__)

    def updateperms(self, action, groups):
        '''
        A method to update the permissions (group membership) of a bugzilla
        user.

        :arg action: add, remove, or set
        :arg groups: list of groups to be added to (i.e. ['fedora_contrib'])
        '''
        self.bugzilla.updateperms(self.name, action, groups)
