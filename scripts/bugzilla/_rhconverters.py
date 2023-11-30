# rhbugzilla.py - a Python interface to Red Hat Bugzilla using xmlrpclib.
#
# Copyright (C) 2008-2012 Red Hat Inc.
# Author: Will Woods <wwoods@redhat.com>
#
# This work is licensed under the GNU GPLv2 or later.
# See the COPYING file in the top-level directory.

from logging import getLogger

from ._util import listify

log = getLogger(__name__)


class _RHBugzillaConverters(object):
    """
    Static class that holds functional Red Hat back compat converters.
    Called inline in Bugzilla
    """
    @staticmethod
    def convert_build_update(
            component=None,
            fixed_in=None,
            qa_whiteboard=None,
            devel_whiteboard=None,
            internal_whiteboard=None,
            sub_component=None):
        adddict = {}

        def get_alias():
            # RHBZ has a custom extension to allow a bug to have multiple
            # aliases, so the format of aliases is
            #    {"add": [...], "remove": [...]}
            # But that means in order to approximate upstream, behavior
            # which just overwrites the existing alias, we need to read
            # the bug's state first to know what string to remove. Which
            # we can't do, since we don't know the bug numbers at this point.
            # So fail for now.
            #
            # The API should provide {"set": [...]}
            # https://bugzilla.redhat.com/show_bug.cgi?id=1173114
            #
            # Implementation will go here when it's available
            pass

        if fixed_in is not None:
            adddict["cf_fixed_in"] = fixed_in
        if qa_whiteboard is not None:
            adddict["cf_qa_whiteboard"] = qa_whiteboard
        if devel_whiteboard is not None:
            adddict["cf_devel_whiteboard"] = devel_whiteboard
        if internal_whiteboard is not None:
            adddict["cf_internal_whiteboard"] = internal_whiteboard

        if sub_component:
            if not isinstance(sub_component, dict):
                component = listify(component)
                if not component:
                    raise ValueError("component must be specified if "
                        "specifying sub_component")
                sub_component = {component[0]: sub_component}
            adddict["sub_components"] = sub_component

        get_alias()

        return adddict


    #################
    # Query methods #
    #################

    @staticmethod
    def pre_translation(query):
        """
        Translates the query for possible aliases
        """
        old = query.copy()

        def split_comma(_v):
            if isinstance(_v, list):
                return _v
            return _v.split(",")

        if 'bug_id' in query:
            query['id'] = split_comma(query.pop('bug_id'))

        if 'component' in query:
            query['component'] = split_comma(query['component'])

        if 'include_fields' not in query and 'column_list' in query:
            query['include_fields'] = query.pop('column_list')

        if old != query:
            log.debug("RHBugzilla pretranslated query to: %s", query)

    @staticmethod
    def post_translation(query, bug):
        """
        Convert the results of getbug back to the ancient RHBZ value
        formats
        """
        ignore = query

        # RHBZ _still_ returns component and version as lists, which
        # deviates from upstream. Copy the list values to components
        # and versions respectively.
        if 'component' in bug and "components" not in bug:
            val = bug['component']
            bug['components'] = isinstance(val, list) and val or [val]
            bug['component'] = bug['components'][0]

        if 'version' in bug and "versions" not in bug:
            val = bug['version']
            bug['versions'] = isinstance(val, list) and val or [val]
            bug['version'] = bug['versions'][0]

        # sub_components isn't too friendly of a format, add a simpler
        # sub_component value
        if 'sub_components' in bug and 'sub_component' not in bug:
            val = bug['sub_components']
            bug['sub_component'] = ""
            if isinstance(val, dict):
                values = []
                for vallist in val.values():
                    values += vallist
                bug['sub_component'] = " ".join(values)
