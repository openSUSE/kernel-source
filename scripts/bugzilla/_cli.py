#!/usr/bin/python3
#
# bugzilla - a commandline frontend for the python bugzilla module
#
# Copyright (C) 2007-2017 Red Hat Inc.
# Author: Will Woods <wwoods@redhat.com>
# Author: Cole Robinson <crobinso@redhat.com>
#
# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the
# Free Software Foundation; either version 2 of the License, or (at your
# option) any later version.  See http://www.gnu.org/copyleft/gpl.html for
# the full text of the license.

from __future__ import print_function

import locale
from logging import getLogger, DEBUG, INFO, WARN, StreamHandler, Formatter
import argparse
import os
import re
import socket
import sys
import tempfile

# pylint: disable=import-error
if sys.version_info[0] >= 3:
    # pylint: disable=no-name-in-module,redefined-builtin
    from xmlrpc.client import Fault, ProtocolError
    from urllib.parse import urlparse
    basestring = (str, bytes)
else:
    from xmlrpclib import Fault, ProtocolError
    from urlparse import urlparse
# pylint: enable=import-error

import requests.exceptions

import bugzilla

DEFAULT_BZ = 'https://apibugzilla.suse.com/xmlrpc.cgi'

format_field_re = re.compile("%{([a-z0-9_]+)(?::([^}]*))?}")

log = getLogger(bugzilla.__name__)


################
# Util helpers #
################

def _is_unittest():
    return bool(os.getenv("__BUGZILLA_UNITTEST"))


def _is_unittest_debug():
    return bool(os.getenv("__BUGZILLA_UNITTEST_DEBUG"))


def to_encoding(ustring):
    string = ''
    if isinstance(ustring, basestring):
        string = ustring
    elif ustring is not None:
        string = str(ustring)

    if sys.version_info[0] >= 3:
        return string

    preferred = locale.getpreferredencoding()
    if _is_unittest():
        preferred = "UTF-8"
    return string.encode(preferred, 'replace')


def open_without_clobber(name, *args):
    '''Try to open the given file with the given mode; if that filename exists,
    try "name.1", "name.2", etc. until we find an unused filename.'''
    fd = None
    count = 1
    orig_name = name
    while fd is None:
        try:
            fd = os.open(name, os.O_CREAT | os.O_EXCL, 0o666)
        except OSError as err:
            if err.errno == os.errno.EEXIST:
                name = "%s.%i" % (orig_name, count)
                count += 1
            else:
                raise IOError(err.errno, err.strerror, err.filename)
    fobj = open(name, *args)
    if fd != fobj.fileno():
        os.close(fd)
    return fobj


def get_default_url():
    """
    Grab a default URL from bugzillarc [DEFAULT] url=X
    """
    from bugzilla.base import _open_bugzillarc
    cfg = _open_bugzillarc()
    if cfg:
        cfgurl = cfg.defaults().get("url", None)
        if cfgurl is not None:
            log.debug("bugzillarc: found cli url=%s", cfgurl)
            return cfgurl
    return DEFAULT_BZ


def setup_logging(debug, verbose):
    handler = StreamHandler(sys.stderr)
    handler.setFormatter(Formatter(
        "[%(asctime)s] %(levelname)s (%(module)s:%(lineno)d) %(message)s",
        "%H:%M:%S"))
    log.addHandler(handler)

    if debug:
        log.setLevel(DEBUG)
    elif verbose:
        log.setLevel(INFO)
    else:
        log.setLevel(WARN)

    if _is_unittest_debug():
        log.setLevel(DEBUG)


##################
# Option parsing #
##################

def _setup_root_parser():
    epilog = 'Try "bugzilla COMMAND --help" for command-specific help.'
    p = argparse.ArgumentParser(epilog=epilog)

    default_url = get_default_url()

    # General bugzilla connection options
    p.add_argument('--bugzilla', default=default_url,
            help="bugzilla XMLRPC URI. default: %s" % default_url)
    p.add_argument("--nosslverify", dest="sslverify",
                 action="store_false", default=True,
                 help="Don't error on invalid bugzilla SSL certificate")
    p.add_argument('--cert',
            help="client side certificate file needed by the webserver")

    p.add_argument('--login', action="store_true",
        help='Run interactive "login" before performing the '
             'specified command.')
    p.add_argument('--username', help="Log in with this username")
    p.add_argument('--password', help="Log in with this password")

    p.add_argument('--ensure-logged-in', action="store_true",
        help="Raise an error if we aren't logged in to bugzilla. "
             "Consider using this if you are depending on "
             "cached credentials, to ensure that when they expire the "
             "tool errors, rather than subtly change output.")
    p.add_argument('--no-cache-credentials',
        action='store_false', default=True, dest='cache_credentials',
        help="Don't save any bugzilla cookies or tokens to disk, and "
             "don't use any pre-existing credentials.")

    p.add_argument('--cookiefile', default=None,
            help="cookie file to use for bugzilla authentication")
    p.add_argument('--tokenfile', default=None,
            help="token file to use for bugzilla authentication")

    p.add_argument('--verbose', action='store_true',
            help="give more info about what's going on")
    p.add_argument('--debug', action='store_true',
            help="output bunches of debugging info")
    p.add_argument('--version', action='version',
                   version=bugzilla.__version__)

    # Allow user to specify BZClass to initialize. Kinda weird for the
    # CLI, I'd rather people file bugs about this so we can fix our detection.
    # So hide it from the help output but keep it for back compat
    p.add_argument('--bztype', default='auto', help=argparse.SUPPRESS)

    return p


def _parser_add_output_options(p):
    outg = p.add_argument_group("Output format options")
    outg.add_argument('--full', action='store_const', dest='output',
            const='full', default='normal',
            help="output detailed bug info")
    outg.add_argument('-i', '--ids', action='store_const', dest='output',
            const='ids', help="output only bug IDs")
    outg.add_argument('-e', '--extra', action='store_const',
            dest='output', const='extra',
            help="output additional bug information "
                 "(keywords, Whiteboards, etc.)")
    outg.add_argument('--oneline', action='store_const', dest='output',
            const='oneline',
            help="one line summary of the bug (useful for scripts)")
    outg.add_argument('--raw', action='store_const', dest='output',
            const='raw', help="raw output of the bugzilla contents")
    outg.add_argument('--outputformat',
            help="Print output in the form given. "
                 "You can use RPM-style tags that match bug "
                 "fields, e.g.: '%%{id}: %%{summary}'. See the man page "
                 "section 'Output options' for more details.")


def _parser_add_bz_fields(rootp, command):
    cmd_new = (command == "new")
    cmd_query = (command == "query")
    cmd_modify = (command == "modify")
    if cmd_new:
        comment_help = "Set initial bug comment/description"
    elif cmd_query:
        comment_help = "Search all bug comments"
    else:
        comment_help = "Add new bug comment"

    p = rootp.add_argument_group("Standard bugzilla options")

    p.add_argument('-p', '--product', help="Product name")
    p.add_argument('-v', '--version', help="Product version")
    p.add_argument('-c', '--component', help="Component name")
    p.add_argument('-t', '--summary', '--short_desc', help="Bug summary")
    p.add_argument('-l', '--comment', '--long_desc', help=comment_help)
    if not cmd_query:
        p.add_argument("--comment-tag", action="append",
                help="Comment tag for the new comment")
    p.add_argument("--sub-component", action="append",
        help="RHBZ sub component field")
    p.add_argument('-o', '--os', help="Operating system")
    p.add_argument('--arch', help="Arch this bug occurs on")
    p.add_argument('-x', '--severity', help="Bug severity")
    p.add_argument('-z', '--priority', help="Bug priority")
    p.add_argument('--alias', help='Bug alias (name)')
    p.add_argument('-s', '--status', '--bug_status',
        help='Bug status (NEW, ASSIGNED, etc.)')
    p.add_argument('-u', '--url', help="URL field")
    p.add_argument('-m', '--target_milestone', help="Target milestone")
    p.add_argument('--target_release', help="RHBZ Target release")

    p.add_argument('--blocked', action="append",
        help="Bug IDs that this bug blocks")
    p.add_argument('--dependson', action="append",
        help="Bug IDs that this bug depends on")
    p.add_argument('--keywords', action="append",
        help="Bug keywords")
    p.add_argument('--groups', action="append",
        help="Which user groups can view this bug")

    p.add_argument('--cc', action="append", help="CC list")
    p.add_argument('-a', '--assigned_to', '--assignee', help="Bug assignee")
    p.add_argument('-q', '--qa_contact', help='QA contact')

    if not cmd_new:
        p.add_argument('-f', '--flag', action='append',
            help="Bug flags state. Ex:\n"
                 "  --flag needinfo?\n"
                 "  --flag dev_ack+ \n"
                 "  clear with --flag needinfoX")
        p.add_argument("--tags", action="append",
                help="Tags/Personal Tags field.")

        p.add_argument('-w', "--whiteboard", '--status_whiteboard',
            action="append", help='Whiteboard field')
        p.add_argument("--devel_whiteboard", action="append",
            help='RHBZ devel whiteboard field')
        p.add_argument("--internal_whiteboard", action="append",
            help='RHBZ internal whiteboard field')
        p.add_argument("--qa_whiteboard", action="append",
            help='RHBZ QA whiteboard field')
        p.add_argument('-F', '--fixed_in',
            help="RHBZ 'Fixed in version' field")

    # Put this at the end, so it sticks out more
    p.add_argument('--field',
        metavar="FIELD=VALUE", action="append", dest="fields",
        help="Manually specify a bugzilla XMLRPC field. FIELD is "
        "the raw name used by the bugzilla instance. For example if your "
        "bugzilla instance has a custom field cf_my_field, do:\n"
        "  --field cf_my_field=VALUE")

    # Used by unit tests, not for end user consumption
    p.add_argument('--__test-return-result', action="store_true",
        dest="test_return_result", help=argparse.SUPPRESS)

    if not cmd_modify:
        _parser_add_output_options(rootp)


def _setup_action_new_parser(subparsers):
    description = ("Create a new bug report. "
        "--product, --component, --version, --summary, and --comment "
        "must be specified. "
        "Options that take multiple values accept comma separated lists, "
        "including --cc, --blocks, --dependson, --groups, and --keywords.")
    p = subparsers.add_parser("new", description=description)

    _parser_add_bz_fields(p, "new")
    p.add_argument('--no-refresh', action='store_true',
                   help='Do not refresh bug after creating')


def _setup_action_query_parser(subparsers):
    description = ("List bug reports that match the given criteria. "
        "Certain options can accept a comma separated list to query multiple "
        "values, including --status, --component, --product, --version, --id.")
    epilog = ("Note: querying via explicit command line options will only "
        "get you so far. See the --from-url option for a way to use powerful "
        "Web UI queries from the command line.")
    p = subparsers.add_parser("query",
        description=description, epilog=epilog)

    _parser_add_bz_fields(p, "query")

    g = p.add_argument_group("'query' specific options")
    g.add_argument('-b', '--id', '--bug_id',
        help="specify individual bugs by IDs, separated with commas")
    g.add_argument('-r', '--reporter',
        help="Email: search reporter email for given address")
    g.add_argument('--quicksearch',
        help="Search using bugzilla's quicksearch functionality.")
    g.add_argument('--savedsearch',
        help="Name of a bugzilla saved search. If you don't own this "
            "saved search, you must passed --savedsearch_sharer_id.")
    g.add_argument('--savedsearch-sharer-id',
        help="Owner ID of the --savedsearch. You can get this ID from "
            "the URL bugzilla generates when running the saved search "
            "from the web UI.")

    # Keep this at the end so it sticks out more
    g.add_argument('--from-url', metavar="WEB_QUERY_URL",
        help="Make a working query via bugzilla's 'Advanced search' web UI, "
             "grab the url from your browser (the string with query.cgi or "
             "buglist.cgi in it), and --from-url will run it via the "
             "bugzilla API. Don't forget to quote the string! "
             "This only works for Bugzilla 5 and Red Hat bugzilla")

    # Deprecated options
    p.add_argument('-E', '--emailtype', help=argparse.SUPPRESS)
    p.add_argument('--components_file', help=argparse.SUPPRESS)
    p.add_argument('-U', '--url_type',
            help=argparse.SUPPRESS)
    p.add_argument('-K', '--keywords_type',
            help=argparse.SUPPRESS)
    p.add_argument('-W', '--status_whiteboard_type',
            help=argparse.SUPPRESS)
    p.add_argument('-B', '--booleantype',
            help=argparse.SUPPRESS)
    p.add_argument('--boolean_query', action="append",
            help=argparse.SUPPRESS)
    p.add_argument('--fixed_in_type', help=argparse.SUPPRESS)


def _setup_action_info_parser(subparsers):
    description = ("List products or component information about the "
        "bugzilla server.")
    p = subparsers.add_parser("info", description=description)

    x = p.add_mutually_exclusive_group(required=True)
    x.add_argument('-p', '--products', action='store_true',
            help='Get a list of products')
    x.add_argument('-c', '--components', metavar="PRODUCT",
            help='List the components in the given product')
    x.add_argument('-o', '--component_owners', metavar="PRODUCT",
            help='List components (and their owners)')
    x.add_argument('-v', '--versions', metavar="PRODUCT",
            help='List the versions for the given product')
    p.add_argument('--active-components', action="store_true",
            help='Only show active components. Combine with --components*')



def _setup_action_modify_parser(subparsers):
    usage = ("bugzilla modify [options] BUGID [BUGID...]\n"
        "Fields that take multiple values have a special input format.\n"
        "Append:    --cc=foo@example.com\n"
        "Overwrite: --cc==foo@example.com\n"
        "Remove:    --cc=-foo@example.com\n"
        "Options that accept this format: --cc, --blocked, --dependson,\n"
        "    --groups, --tags, whiteboard fields.")
    p = subparsers.add_parser("modify", usage=usage)

    _parser_add_bz_fields(p, "modify")

    g = p.add_argument_group("'modify' specific options")
    g.add_argument("ids", nargs="+", help="Bug IDs to modify")
    g.add_argument('-k', '--close', metavar="RESOLUTION",
        help='Close with the given resolution (WONTFIX, NOTABUG, etc.)')
    g.add_argument('-d', '--dupeid', metavar="ORIGINAL",
        help='ID of original bug. Implies --close DUPLICATE')
    g.add_argument('--private', action='store_true', default=False,
        help='Mark new comment as private')
    g.add_argument('--reset-assignee', action="store_true",
        help='Reset assignee to component default')
    g.add_argument('--reset-qa-contact', action="store_true",
        help='Reset QA contact to component default')


def _setup_action_attach_parser(subparsers):
    usage = """
bugzilla attach --file=FILE --desc=DESC [--type=TYPE] BUGID [BUGID...]
bugzilla attach --get=ATTACHID --getall=BUGID [...]
bugzilla attach --type=TYPE BUGID [BUGID...]"""
    description = "Attach files or download attachments."
    p = subparsers.add_parser("attach", description=description, usage=usage)

    p.add_argument("ids", nargs="*", help="BUGID references")
    p.add_argument('-f', '--file', metavar="FILENAME",
            help='File to attach, or filename for data provided on stdin')
    p.add_argument('-d', '--description', '--summary',
            metavar="SUMMARY", dest='desc',
            help="A short summary of the file being attached")
    p.add_argument('-t', '--type', metavar="MIMETYPE",
            help="Mime-type for the file being attached")
    p.add_argument('-g', '--get', metavar="ATTACHID", action="append",
            default=[], help="Download the attachment with the given ID")
    p.add_argument("--getall", "--get-all", metavar="BUGID", action="append",
            default=[], help="Download all attachments on the given bug")
    p.add_argument('-l', '--comment', '--long_desc', help="Add comment with attachment")


def _setup_action_login_parser(subparsers):
    usage = 'bugzilla login [username [password]]'
    description = "Log into bugzilla and save a login cookie or token."
    p = subparsers.add_parser("login", description=description, usage=usage)
    p.add_argument("pos_username", nargs="?", help="Optional username",
            metavar="username")
    p.add_argument("pos_password", nargs="?", help="Optional password",
            metavar="password")


def setup_parser():
    rootparser = _setup_root_parser()
    subparsers = rootparser.add_subparsers(dest="command")
    subparsers.required = True
    _setup_action_new_parser(subparsers)
    _setup_action_query_parser(subparsers)
    _setup_action_info_parser(subparsers)
    _setup_action_modify_parser(subparsers)
    _setup_action_attach_parser(subparsers)
    _setup_action_login_parser(subparsers)
    return rootparser


####################
# Command routines #
####################

def _merge_field_opts(query, opt, parser):
    # Add any custom fields if specified
    if opt.fields is None:
        return

    for f in opt.fields:
        try:
            f, v = f.split('=', 1)
            query[f] = v
        except Exception:
            parser.error("Invalid field argument provided: %s" % (f))


def _do_query(bz, opt, parser):
    q = {}

    # Parse preconstructed queries.
    u = opt.from_url
    if u:
        q = bz.url_to_query(u)

    if opt.components_file:
        # Components slurped in from file (one component per line)
        # This can be made more robust
        clist = []
        f = open(opt.components_file, 'r')
        for line in f.readlines():
            line = line.rstrip("\n")
            clist.append(line)
        opt.component = clist

    if opt.status:
        val = opt.status
        stat = val
        if val == 'ALL':
            # leaving this out should return bugs of any status
            stat = None
        elif val == 'DEV':
            # Alias for all development bug statuses
            stat = ['NEW', 'ASSIGNED', 'NEEDINFO', 'ON_DEV',
                'MODIFIED', 'POST', 'REOPENED']
        elif val == 'QE':
            # Alias for all QE relevant bug statuses
            stat = ['ASSIGNED', 'ON_QA', 'FAILS_QA', 'PASSES_QA']
        elif val == 'EOL':
            # Alias for EndOfLife bug statuses
            stat = ['VERIFIED', 'RELEASE_PENDING', 'RESOLVED']
        elif val == 'OPEN':
            # non-Closed statuses
            stat = ['NEW', 'ASSIGNED', 'MODIFIED', 'ON_DEV', 'ON_QA',
                'VERIFIED', 'RELEASE_PENDING', 'POST']
        opt.status = stat

    # Convert all comma separated list parameters to actual lists,
    # which is what bugzilla wants
    # According to bugzilla docs, any parameter can be a list, but
    # let's only do this for options we explicitly mention can be
    # comma separated.
    for optname in ["severity", "id", "status", "component",
                    "priority", "product", "version"]:
        val = getattr(opt, optname, None)
        if not isinstance(val, str):
            continue
        setattr(opt, optname, val.split(","))

    include_fields = None
    if opt.output == 'raw':
        # 'raw' always does a getbug() call anyways, so just ask for ID back
        include_fields = ['id']

    elif opt.outputformat:
        include_fields = []
        for fieldname, rest in format_field_re.findall(opt.outputformat):
            if fieldname == "whiteboard" and rest:
                fieldname = rest + "_" + fieldname
            elif fieldname == "flag":
                fieldname = "flags"
            elif fieldname == "cve":
                fieldname = ["keywords", "blocks"]
            elif fieldname == "__unicode__":
                # Needs to be in sync with bug.__unicode__
                fieldname = ["id", "status", "assigned_to", "summary"]

            flist = isinstance(fieldname, list) and fieldname or [fieldname]
            for f in flist:
                if f not in include_fields:
                    include_fields.append(f)

    if include_fields is not None:
        include_fields.sort()

    built_query = bz.build_query(
        product=opt.product or None,
        component=opt.component or None,
        sub_component=opt.sub_component or None,
        version=opt.version or None,
        reporter=opt.reporter or None,
        bug_id=opt.id or None,
        short_desc=opt.summary or None,
        long_desc=opt.comment or None,
        cc=opt.cc or None,
        assigned_to=opt.assigned_to or None,
        qa_contact=opt.qa_contact or None,
        status=opt.status or None,
        blocked=opt.blocked or None,
        dependson=opt.dependson or None,
        keywords=opt.keywords or None,
        keywords_type=opt.keywords_type or None,
        url=opt.url or None,
        url_type=opt.url_type or None,
        status_whiteboard=opt.whiteboard or None,
        status_whiteboard_type=opt.status_whiteboard_type or None,
        fixed_in=opt.fixed_in or None,
        fixed_in_type=opt.fixed_in_type or None,
        flag=opt.flag or None,
        alias=opt.alias or None,
        qa_whiteboard=opt.qa_whiteboard or None,
        devel_whiteboard=opt.devel_whiteboard or None,
        boolean_query=opt.boolean_query or None,
        bug_severity=opt.severity or None,
        priority=opt.priority or None,
        target_release=opt.target_release or None,
        target_milestone=opt.target_milestone or None,
        emailtype=opt.emailtype or None,
        booleantype=opt.booleantype or None,
        include_fields=include_fields,
        quicksearch=opt.quicksearch or None,
        savedsearch=opt.savedsearch or None,
        savedsearch_sharer_id=opt.savedsearch_sharer_id or None,
        tags=opt.tags or None)

    _merge_field_opts(built_query, opt, parser)

    built_query.update(q)
    q = built_query

    if not q:
        parser.error("'query' command requires additional arguments")
    if opt.test_return_result:
        return q
    return bz.query(q)


def _do_info(bz, opt):
    """
    Handle the 'info' subcommand
    """
    # All these commands call getproducts internally, so do it up front
    # with minimal include_fields for speed
    def _filter_components(compdetails):
        ret = {}
        for k, v in compdetails.items():
            if v.get("is_active", True):
                ret[k] = v
        return ret

    productname = (opt.components or opt.component_owners or opt.versions)
    include_fields = ["name", "id"]
    fastcomponents = (opt.components and not opt.active_components)
    if opt.versions:
        include_fields += ["versions"]
    if opt.component_owners:
        include_fields += [
            "components.default_assigned_to",
            "components.name",
        ]
    if (opt.active_components and
        any(["components" in i for i in include_fields])):
        include_fields += ["components.is_active"]

    bz.refresh_products(names=productname and [productname] or None,
            include_fields=include_fields)

    if opt.products:
        for name in sorted([p["name"] for p in bz.getproducts()]):
            print(name)

    elif fastcomponents:
        for name in sorted(bz.getcomponents(productname)):
            print(name)

    elif opt.components:
        details = bz.getcomponentsdetails(productname)
        for name in sorted(_filter_components(details)):
            print(name)

    elif opt.versions:
        proddict = bz.getproducts()[0]
        for v in proddict['versions']:
            if v["is_active"]:
                print(to_encoding(v["name"]))

    elif opt.component_owners:
        details = bz.getcomponentsdetails(productname)
        for c in sorted(_filter_components(details)):
            print(to_encoding(u"%s: %s" % (c,
                details[c]['default_assigned_to'])))


def _convert_to_outputformat(output):
    fmt = ""

    if output == "normal":
        fmt = "%{__unicode__}"

    elif output == "ids":
        fmt = "%{id}"

    elif output == 'full':
        fmt += "%{__unicode__}\n"
        fmt += "Component: %{component}\n"
        fmt += "CC: %{cc}\n"
        fmt += "Blocked: %{blocks}\n"
        fmt += "Depends: %{depends_on}\n"
        fmt += "%{comments}\n"

    elif output == 'extra':
        fmt += "%{__unicode__}\n"
        fmt += " +Keywords: %{keywords}\n"
        fmt += " +QA Whiteboard: %{qa_whiteboard}\n"
        fmt += " +Status Whiteboard: %{status_whiteboard}\n"
        fmt += " +Devel Whiteboard: %{devel_whiteboard}\n"

    elif output == 'oneline':
        fmt += "#%{bug_id} %{status} %{assigned_to} %{component}\t"
        fmt += "[%{target_milestone}] %{flags} %{cve}"

    else:
        raise RuntimeError("Unknown output type '%s'" % output)

    return fmt


def _format_output(bz, opt, buglist):
    if opt.output == 'raw':
        buglist = bz.getbugs([b.bug_id for b in buglist])
        for b in buglist:
            print("Bugzilla %s: " % b.bug_id)
            for attrname in sorted(b.__dict__):
                print(to_encoding(u"ATTRIBUTE[%s]: %s" %
                                  (attrname, b.__dict__[attrname])))
            print("\n\n")
        return

    def bug_field(matchobj):
        # whiteboard and flag allow doing
        #   %{whiteboard:devel} and %{flag:needinfo}
        # That's what 'rest' matches
        (fieldname, rest) = matchobj.groups()

        if fieldname == "whiteboard" and rest:
            fieldname = rest + "_" + fieldname

        if fieldname == "flag" and rest:
            val = b.get_flag_status(rest)

        elif fieldname == "flags" or fieldname == "flags_requestee":
            tmpstr = []
            for f in getattr(b, "flags", []):
                requestee = f.get('requestee', "")
                if fieldname == "flags":
                    requestee = ""
                if fieldname == "flags_requestee":
                    if requestee == "":
                        continue
                    tmpstr.append("%s" % requestee)
                else:
                    tmpstr.append("%s%s%s" %
                            (f['name'], f['status'], requestee))

            val = ",".join(tmpstr)

        elif fieldname == "cve":
            cves = []
            for key in getattr(b, "keywords", []):
                # grab CVE from keywords and blockers
                if key.find("Security") == -1:
                    continue
                for bl in b.blocks:
                    cvebug = bz.getbug(bl)
                    for cb in cvebug.alias:
                        if cb.find("CVE") == -1:
                            continue
                        if cb.strip() not in cves:
                            cves.append(cb)
            val = ",".join(cves)

        elif fieldname == "comments":
            val = ""
            for c in getattr(b, "comments", []):
                val += ("\n* %s - %s:\n%s\n" % (c['time'],
                         c.get("creator", c.get("author", "")), c['text']))

        elif fieldname == "external_bugs":
            val = ""
            for e in getattr(b, "external_bugs", []):
                url = e["type"]["full_url"].replace("%id%", e["ext_bz_bug_id"])
                if not val:
                    val += "\n"
                val += "External bug: %s\n" % url

        elif fieldname == "__unicode__":
            val = b.__unicode__()
        else:
            val = getattr(b, fieldname, "")

        vallist = isinstance(val, list) and val or [val]
        val = ','.join([to_encoding(v) for v in vallist])

        return val

    for b in buglist:
        print(format_field_re.sub(bug_field, opt.outputformat))


def _parse_triset(vallist, checkplus=True, checkminus=True, checkequal=True,
                  splitcomma=False):
    add_val = []
    rm_val = []
    set_val = None

    def make_list(v):
        if not v:
            return []
        if splitcomma:
            return v.split(",")
        return [v]

    for val in isinstance(vallist, list) and vallist or [vallist]:
        val = val or ""

        if val.startswith("+") and checkplus:
            add_val += make_list(val[1:])
        elif val.startswith("-") and checkminus:
            rm_val += make_list(val[1:])
        elif val.startswith("=") and checkequal:
            # Intentionally overwrite this
            set_val = make_list(val[1:])
        else:
            add_val += make_list(val)

    return add_val, rm_val, set_val


def _do_new(bz, opt, parser):
    # Parse options that accept comma separated list
    def parse_multi(val):
        return _parse_triset(val, checkplus=False, checkminus=False,
                             checkequal=False, splitcomma=True)[0]

    ret = bz.build_createbug(
        blocks=parse_multi(opt.blocked) or None,
        cc=parse_multi(opt.cc) or None,
        component=opt.component or None,
        depends_on=parse_multi(opt.dependson) or None,
        description=opt.comment or None,
        groups=parse_multi(opt.groups) or None,
        keywords=parse_multi(opt.keywords) or None,
        op_sys=opt.os or None,
        platform=opt.arch or None,
        priority=opt.priority or None,
        product=opt.product or None,
        severity=opt.severity or None,
        summary=opt.summary or None,
        url=opt.url or None,
        version=opt.version or None,
        assigned_to=opt.assigned_to or None,
        qa_contact=opt.qa_contact or None,
        sub_component=opt.sub_component or None,
        alias=opt.alias or None,
        comment_tags=opt.comment_tag or None,
    )

    _merge_field_opts(ret, opt, parser)

    if opt.test_return_result:
        return ret

    b = bz.createbug(ret)
    if not opt.no_refresh:
        b.refresh()
    return [b]


def _do_modify(bz, parser, opt):
    bugid_list = [bugid for a in opt.ids for bugid in a.split(',')]

    add_wb, rm_wb, set_wb = _parse_triset(opt.whiteboard)
    add_devwb, rm_devwb, set_devwb = _parse_triset(opt.devel_whiteboard)
    add_intwb, rm_intwb, set_intwb = _parse_triset(opt.internal_whiteboard)
    add_qawb, rm_qawb, set_qawb = _parse_triset(opt.qa_whiteboard)

    add_blk, rm_blk, set_blk = _parse_triset(opt.blocked, splitcomma=True)
    add_deps, rm_deps, set_deps = _parse_triset(opt.dependson, splitcomma=True)
    add_key, rm_key, set_key = _parse_triset(opt.keywords)
    add_cc, rm_cc, ignore = _parse_triset(opt.cc,
                                          checkplus=False,
                                          checkequal=False)
    add_groups, rm_groups, ignore = _parse_triset(opt.groups,
                                                  checkequal=False,
                                                  splitcomma=True)
    add_tags, rm_tags, ignore = _parse_triset(opt.tags, checkequal=False)

    status = opt.status or None
    if opt.dupeid is not None:
        opt.close = "DUPLICATE"
    if opt.close:
        status = "RESOLVED"

    flags = []
    if opt.flag:
        # Convert "foo+" to tuple ("foo", "+")
        for f in opt.flag:
            flags.append({"name": f[:-1], "status": f[-1]})

    update = bz.build_update(
        assigned_to=opt.assigned_to or None,
        comment=opt.comment or None,
        comment_private=opt.private or None,
        component=opt.component or None,
        product=opt.product or None,
        blocks_add=add_blk or None,
        blocks_remove=rm_blk or None,
        blocks_set=set_blk,
        url=opt.url or None,
        cc_add=add_cc or None,
        cc_remove=rm_cc or None,
        depends_on_add=add_deps or None,
        depends_on_remove=rm_deps or None,
        depends_on_set=set_deps,
        groups_add=add_groups or None,
        groups_remove=rm_groups or None,
        keywords_add=add_key or None,
        keywords_remove=rm_key or None,
        keywords_set=set_key,
        op_sys=opt.os or None,
        platform=opt.arch or None,
        priority=opt.priority or None,
        qa_contact=opt.qa_contact or None,
        severity=opt.severity or None,
        status=status,
        summary=opt.summary or None,
        version=opt.version or None,
        reset_assigned_to=opt.reset_assignee or None,
        reset_qa_contact=opt.reset_qa_contact or None,
        resolution=opt.close or None,
        target_release=opt.target_release or None,
        target_milestone=opt.target_milestone or None,
        dupe_of=opt.dupeid or None,
        fixed_in=opt.fixed_in or None,
        whiteboard=set_wb and set_wb[0] or None,
        devel_whiteboard=set_devwb and set_devwb[0] or None,
        internal_whiteboard=set_intwb and set_intwb[0] or None,
        qa_whiteboard=set_qawb and set_qawb[0] or None,
        sub_component=opt.sub_component or None,
        alias=opt.alias or None,
        flags=flags or None,
        comment_tags=opt.comment_tag or None,
    )

    # We make this a little convoluted to facilitate unit testing
    wbmap = {
        "whiteboard": (add_wb, rm_wb),
        "internal_whiteboard": (add_intwb, rm_intwb),
        "qa_whiteboard": (add_qawb, rm_qawb),
        "devel_whiteboard": (add_devwb, rm_devwb),
    }

    for k, v in wbmap.copy().items():
        if not v[0] and not v[1]:
            del(wbmap[k])

    _merge_field_opts(update, opt, parser)

    log.debug("update bug dict=%s", update)
    log.debug("update whiteboard dict=%s", wbmap)

    if not any([update, wbmap, add_tags, rm_tags]):
        parser.error("'modify' command requires additional arguments")

    if opt.test_return_result:
        return (update, wbmap, add_tags, rm_tags)

    if add_tags or rm_tags:
        ret = bz.update_tags(bugid_list,
            tags_add=add_tags, tags_remove=rm_tags)
        log.debug("bz.update_tags returned=%s", ret)
    if update:
        ret = bz.update_bugs(bugid_list, update)
        log.debug("bz.update_bugs returned=%s", ret)

    if not wbmap:
        return

    # Now for the things we can't blindly batch.
    # Being able to prepend/append to whiteboards, which are just
    # plain string values, is an old rhbz semantic that we try to maintain
    # here. This is a bit weird for traditional bugzilla XMLRPC
    log.debug("Adjusting whiteboard fields one by one")
    for bug in bz.getbugs(bugid_list):
        for wb, (add_list, rm_list) in wbmap.items():
            for tag in add_list:
                newval = getattr(bug, wb) or ""
                if newval:
                    newval += " "
                newval += tag
                bz.update_bugs([bug.id],
                               bz.build_update(**{wb: newval}))

            for tag in rm_list:
                newval = (getattr(bug, wb) or "").split()
                for t in newval[:]:
                    if t == tag:
                        newval.remove(t)
                bz.update_bugs([bug.id],
                               bz.build_update(**{wb: " ".join(newval)}))


def _do_get_attach(bz, opt):
    for bug in bz.getbugs(opt.getall):
        opt.get += bug.get_attachment_ids()

    for attid in set(opt.get):
        att = bz.openattachment(attid)
        outfile = open_without_clobber(att.name, "wb")
        data = att.read(4096)
        while data:
            outfile.write(data)
            data = att.read(4096)
        print("Wrote %s" % outfile.name)

    return


def _do_set_attach(bz, opt, parser):
    if not opt.ids:
        parser.error("Bug ID must be specified for setting attachments")

    if sys.stdin.isatty():
        if not opt.file:
            parser.error("--file must be specified")
        fileobj = open(opt.file, "rb")
    else:
        # piped input on stdin
        if not opt.desc:
            parser.error("--description must be specified if passing "
                         "file on stdin")

        fileobj = tempfile.NamedTemporaryFile(prefix="bugzilla-attach.")
        data = sys.stdin.read(4096)

        while data:
            fileobj.write(data.encode(locale.getpreferredencoding()))
            data = sys.stdin.read(4096)
        fileobj.seek(0)

    kwargs = {}
    if opt.file:
        kwargs["filename"] = os.path.basename(opt.file)
    if opt.type:
        kwargs["contenttype"] = opt.type
    if opt.type in ["text/x-patch"]:
        kwargs["ispatch"] = True
    if opt.comment:
        kwargs["comment"] = opt.comment
    desc = opt.desc or os.path.basename(fileobj.name)

    # Upload attachments
    for bugid in opt.ids:
        attid = bz.attachfile(bugid, fileobj, desc, **kwargs)
        print("Created attachment %i on bug %s" % (attid, bugid))


#################
# Main handling #
#################

def _make_bz_instance(opt):
    """
    Build the Bugzilla instance we will use
    """
    if opt.bztype != 'auto':
        log.info("Explicit --bztype is no longer supported, ignoring")

    cookiefile = None
    tokenfile = None
    if opt.cache_credentials:
        cookiefile = opt.cookiefile or -1
        tokenfile = opt.tokenfile or -1

    bz = bugzilla.Bugzilla(
        url=opt.bugzilla,
        cookiefile=cookiefile,
        tokenfile=tokenfile,
        sslverify=opt.sslverify,
        cert=opt.cert)
    return bz


def _handle_login(opt, action, bz):
    """
    Handle all login related bits
    """
    is_login_command = (action == 'login')

    do_interactive_login = (is_login_command or
        opt.login or opt.username or opt.password)
    username = getattr(opt, "pos_username", None) or opt.username
    password = getattr(opt, "pos_password", None) or opt.password

    try:
        if do_interactive_login:
            if bz.url:
                print("Logging into %s" % urlparse(bz.url)[1])
            bz.interactive_login(username, password)
    except bugzilla.BugzillaError as e:
        print(str(e))
        sys.exit(1)

    if opt.ensure_logged_in and not bz.logged_in:
        print("--ensure-logged-in passed but you aren't logged in to %s" %
            bz.url)
        sys.exit(1)

    if is_login_command:
        msg = "Login successful."
        if bz.cookiefile or bz.tokenfile:
            msg = "Login successful, token cache updated."

        print(msg)
        sys.exit(0)


def _main(unittest_bz_instance):
    parser = setup_parser()
    opt = parser.parse_args()
    action = opt.command
    setup_logging(opt.debug, opt.verbose)

    log.debug("Launched with command line: %s", " ".join(sys.argv))

    # Connect to bugzilla
    log.info('Connecting to %s', opt.bugzilla)

    if unittest_bz_instance:
        bz = unittest_bz_instance
    else:
        bz = _make_bz_instance(opt)

    # Handle login options
    _handle_login(opt, action, bz)


    ###########################
    # Run the actual commands #
    ###########################

    if hasattr(opt, "outputformat"):
        if not opt.outputformat and opt.output not in ['raw', None]:
            opt.outputformat = _convert_to_outputformat(opt.output)

    buglist = []
    if action == 'info':
        if not (opt.products or
                opt.components or
                opt.component_owners or
                opt.versions):
            parser.error("'info' command requires additional arguments")

        _do_info(bz, opt)

    elif action == 'query':
        buglist = _do_query(bz, opt, parser)
        if opt.test_return_result:
            return buglist

    elif action == 'new':
        buglist = _do_new(bz, opt, parser)
        if opt.test_return_result:
            return buglist

    elif action == 'attach':
        if opt.get or opt.getall:
            if opt.ids:
                parser.error("Bug IDs '%s' not used for "
                    "getting attachments" % opt.ids)
            _do_get_attach(bz, opt)
        else:
            _do_set_attach(bz, opt, parser)

    elif action == 'modify':
        modout = _do_modify(bz, parser, opt)
        if opt.test_return_result:
            return modout
    else:
        raise RuntimeError("Unexpected action '%s'" % action)

    # If we're doing new/query/modify, output our results
    if action in ['new', 'query']:
        _format_output(bz, opt, buglist)


def main(unittest_bz_instance=None):
    try:
        try:
            return _main(unittest_bz_instance)
        except (Exception, KeyboardInterrupt):
            log.debug("", exc_info=True)
            raise
    except (Fault, bugzilla.BugzillaError) as e:
        print("\nServer error: %s" % str(e))
        sys.exit(3)
    except requests.exceptions.SSLError as e:
        # Give SSL recommendations
        print("SSL error: %s" % e)
        print("\nIf you trust the remote server, you can work "
              "around this error with:\n"
              "  bugzilla --nosslverify ...")
        sys.exit(4)
    except (socket.error,
            requests.exceptions.HTTPError,
            requests.exceptions.ConnectionError,
            ProtocolError) as e:
        print("\nConnection lost/failed: %s" % str(e))
        sys.exit(2)


def cli():
    try:
        main()
    except KeyboardInterrupt:
        log.debug("", exc_info=True)
        print("\nExited at user request.")
        sys.exit(1)
