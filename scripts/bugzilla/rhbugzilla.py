# rhbugzilla.py - a Python interface to Red Hat Bugzilla using xmlrpclib.
#
# Copyright (C) 2008-2012 Red Hat Inc.
# Author: Will Woods <wwoods@redhat.com>
#
# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the
# Free Software Foundation; either version 2 of the License, or (at your
# option) any later version.  See http://www.gnu.org/copyleft/gpl.html for
# the full text of the license.

from logging import getLogger

from .base import Bugzilla

log = getLogger(__name__)


class RHBugzilla(Bugzilla):
    '''
    Bugzilla class for connecting Red Hat's forked bugzilla instance,
    bugzilla.redhat.com

    Historically this class used many more non-upstream methods, but
    in 2012 RH started dropping most of its custom bits. By that time,
    upstream BZ had most of the important functionality.

    Much of the remaining code here is just trying to keep things operating
    in python-bugzilla back compatible manner.

    This class was written using bugzilla.redhat.com's API docs:
    https://bugzilla.redhat.com/docs/en/html/api/
    '''
    def _init_class_state(self):
        def _add_both_alias(newname, origname):
            self._add_field_alias(newname, origname, is_api=False)
            self._add_field_alias(origname, newname, is_bug=False)

        _add_both_alias('fixed_in', 'cf_fixed_in')
        _add_both_alias('qa_whiteboard', 'cf_qa_whiteboard')
        _add_both_alias('devel_whiteboard', 'cf_devel_whiteboard')
        _add_both_alias('internal_whiteboard', 'cf_internal_whiteboard')

        self._add_field_alias('component', 'components', is_bug=False)
        self._add_field_alias('version', 'versions', is_bug=False)
        # Yes, sub_components is the field name the API expects
        self._add_field_alias('sub_components', 'sub_component', is_bug=False)

        # flags format isn't exactly the same but it's the closest approx
        self._add_field_alias('flags', 'flag_types')

        self._getbug_extra_fields = self._getbug_extra_fields + [
            "comments", "description",
            "external_bugs", "flags", "sub_components",
            "tags",
        ]
        self._supports_getbug_extra_fields = True


    ######################
    # Bug update methods #
    ######################

    def build_update(self, **kwargs):
        # pylint: disable=arguments-differ
        adddict = {}

        def pop(key, destkey):
            val = kwargs.pop(key, None)
            if val is None:
                return
            adddict[destkey] = val

        def get_sub_component():
            val = kwargs.pop("sub_component", None)
            if val is None:
                return

            if not isinstance(val, dict):
                component = self._listify(kwargs.get("component"))
                if not component:
                    raise ValueError("component must be specified if "
                        "specifying sub_component")
                val = {component[0]: val}
            adddict["sub_components"] = val

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

        pop("fixed_in", "cf_fixed_in")
        pop("qa_whiteboard", "cf_qa_whiteboard")
        pop("devel_whiteboard", "cf_devel_whiteboard")
        pop("internal_whiteboard", "cf_internal_whiteboard")

        get_sub_component()
        get_alias()

        vals = Bugzilla.build_update(self, **kwargs)
        vals.update(adddict)

        return vals

    def add_external_tracker(self, bug_ids, ext_bz_bug_id, ext_type_id=None,
                             ext_type_description=None, ext_type_url=None,
                             ext_status=None, ext_description=None,
                             ext_priority=None):
        """
        Wrapper method to allow adding of external tracking bugs using the
        ExternalBugs::WebService::add_external_bug method.

        This is documented at
        https://bugzilla.redhat.com/docs/en/html/api/extensions/ExternalBugs/lib/WebService.html#add_external_bug

        bug_ids: A single bug id or list of bug ids to have external trackers
            added.
        ext_bz_bug_id: The external bug id (ie: the bug number in the
            external tracker).
        ext_type_id: The external tracker id as used by Bugzilla.
        ext_type_description: The external tracker description as used by
            Bugzilla.
        ext_type_url: The external tracker url as used by Bugzilla.
        ext_status: The status of the external bug.
        ext_description: The description of the external bug.
        ext_priority: The priority of the external bug.
        """
        param_dict = {'ext_bz_bug_id': ext_bz_bug_id}
        if ext_type_id is not None:
            param_dict['ext_type_id'] = ext_type_id
        if ext_type_description is not None:
            param_dict['ext_type_description'] = ext_type_description
        if ext_type_url is not None:
            param_dict['ext_type_url'] = ext_type_url
        if ext_status is not None:
            param_dict['ext_status'] = ext_status
        if ext_description is not None:
            param_dict['ext_description'] = ext_description
        if ext_priority is not None:
            param_dict['ext_priority'] = ext_priority
        params = {
            'bug_ids': self._listify(bug_ids),
            'external_bugs': [param_dict],
        }

        log.debug("Calling ExternalBugs.add_external_bug(%s)", params)
        return self._proxy.ExternalBugs.add_external_bug(params)

    def update_external_tracker(self, ids=None, ext_type_id=None,
                                ext_type_description=None, ext_type_url=None,
                                ext_bz_bug_id=None, bug_ids=None,
                                ext_status=None, ext_description=None,
                                ext_priority=None):
        """
        Wrapper method to allow adding of external tracking bugs using the
        ExternalBugs::WebService::update_external_bug method.

        This is documented at
        https://bugzilla.redhat.com/docs/en/html/api/extensions/ExternalBugs/lib/WebService.html#update_external_bug

        ids: A single external tracker bug id or list of external tracker bug
            ids.
        ext_type_id: The external tracker id as used by Bugzilla.
        ext_type_description: The external tracker description as used by
            Bugzilla.
        ext_type_url: The external tracker url as used by Bugzilla.
        ext_bz_bug_id: A single external bug id or list of external bug ids
            (ie: the bug number in the external tracker).
        bug_ids: A single bug id or list of bug ids to have external tracker
            info updated.
        ext_status: The status of the external bug.
        ext_description: The description of the external bug.
        ext_priority: The priority of the external bug.
        """
        params = {}
        if ids is not None:
            params['ids'] = self._listify(ids)
        if ext_type_id is not None:
            params['ext_type_id'] = ext_type_id
        if ext_type_description is not None:
            params['ext_type_description'] = ext_type_description
        if ext_type_url is not None:
            params['ext_type_url'] = ext_type_url
        if ext_bz_bug_id is not None:
            params['ext_bz_bug_id'] = self._listify(ext_bz_bug_id)
        if bug_ids is not None:
            params['bug_ids'] = self._listify(bug_ids)
        if ext_status is not None:
            params['ext_status'] = ext_status
        if ext_description is not None:
            params['ext_description'] = ext_description
        if ext_priority is not None:
            params['ext_priority'] = ext_priority

        log.debug("Calling ExternalBugs.update_external_bug(%s)", params)
        return self._proxy.ExternalBugs.update_external_bug(params)

    def remove_external_tracker(self, ids=None, ext_type_id=None,
                                ext_type_description=None, ext_type_url=None,
                                ext_bz_bug_id=None, bug_ids=None):
        """
        Wrapper method to allow removal of external tracking bugs using the
        ExternalBugs::WebService::remove_external_bug method.

        This is documented at
        https://bugzilla.redhat.com/docs/en/html/api/extensions/ExternalBugs/lib/WebService.html#remove_external_bug

        ids: A single external tracker bug id or list of external tracker bug
            ids.
        ext_type_id: The external tracker id as used by Bugzilla.
        ext_type_description: The external tracker description as used by
            Bugzilla.
        ext_type_url: The external tracker url as used by Bugzilla.
        ext_bz_bug_id: A single external bug id or list of external bug ids
            (ie: the bug number in the external tracker).
        bug_ids: A single bug id or list of bug ids to have external tracker
            info updated.
        """
        params = {}
        if ids is not None:
            params['ids'] = self._listify(ids)
        if ext_type_id is not None:
            params['ext_type_id'] = ext_type_id
        if ext_type_description is not None:
            params['ext_type_description'] = ext_type_description
        if ext_type_url is not None:
            params['ext_type_url'] = ext_type_url
        if ext_bz_bug_id is not None:
            params['ext_bz_bug_id'] = self._listify(ext_bz_bug_id)
        if bug_ids is not None:
            params['bug_ids'] = self._listify(bug_ids)

        log.debug("Calling ExternalBugs.remove_external_bug(%s)", params)
        return self._proxy.ExternalBugs.remove_external_bug(params)


    #################
    # Query methods #
    #################

    def pre_translation(self, query):
        '''Translates the query for possible aliases'''
        old = query.copy()

        if 'bug_id' in query:
            if not isinstance(query['bug_id'], list):
                query['id'] = query['bug_id'].split(',')
            else:
                query['id'] = query['bug_id']
            del query['bug_id']

        if 'component' in query:
            if not isinstance(query['component'], list):
                query['component'] = query['component'].split(',')

        if 'include_fields' not in query and 'column_list' not in query:
            return

        if 'include_fields' not in query:
            query['include_fields'] = []
            if 'column_list' in query:
                query['include_fields'] = query['column_list']
                del query['column_list']

        # We need to do this for users here for users that
        # don't call build_query
        query.update(self._process_include_fields(query["include_fields"],
            None, None))

        if old != query:
            log.debug("RHBugzilla pretranslated query to: %s", query)

    def post_translation(self, query, bug):
        '''
        Convert the results of getbug back to the ancient RHBZ value
        formats
        '''
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

    def build_external_tracker_boolean_query(self, *args, **kwargs):
        ignore1 = args
        ignore2 = kwargs
        raise RuntimeError("Building external boolean queries is "
            "no longer supported. Please build a URL query "
            "via the bugzilla web UI and pass it to 'query --from-url' "
            "or url_to_query()")


    def build_query(self, **kwargs):
        # pylint: disable=arguments-differ

        # We previously accepted a text format to approximate boolean
        # queries, and only for RHBugzilla. Upstream bz has --from-url
        # support now, so point people to that instead so we don't have
        # to document and maintain this logic anymore
        def _warn_bool(kwkey):
            vallist = self._listify(kwargs.get(kwkey, None))
            for value in vallist or []:
                for s in value.split(" "):
                    if s not in ["|", "&", "!"]:
                        continue
                    log.warning("%s value '%s' appears to use the now "
                        "unsupported boolean formatting, your query may "
                        "be incorrect. If you need complicated URL queries, "
                        "look into bugzilla --from-url/url_to_query().",
                        kwkey, value)
                    return

        _warn_bool("fixed_in")
        _warn_bool("blocked")
        _warn_bool("dependson")
        _warn_bool("flag")
        _warn_bool("qa_whiteboard")
        _warn_bool("devel_whiteboard")
        _warn_bool("alias")

        return Bugzilla.build_query(self, **kwargs)
