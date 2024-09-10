#!/usr/bin/env python3
#
# bugzilla - a commandline frontend for the python bugzilla module
#
# Copyright (C) 2007-2017 Red Hat Inc.
# Author: Will Woods <wwoods@redhat.com>
# Author: Cole Robinson <crobinso@redhat.com>
#
# This work is licensed under the GNU GPLv2 or later.
# See the COPYING file in the top-level directory.

import argparse
import base64
import datetime
import errno
import json
import locale
from logging import getLogger, DEBUG, INFO, WARN, StreamHandler, Formatter
import os
import re
import socket
import sys
import tempfile
import urllib.parse
import xmlrpc.client

import requests.exceptions

import bugzilla


DEFAULT_BZ = 'https://apibugzilla.suse.com'

format_field_re = re.compile("%{([a-z0-9_]+)(?::([^}]*))?}")

log = getLogger(bugzilla.__name__)


################
# Util helpers #
################

def _is_unittest_debug():
    return bool(os.getenv("__BUGZILLA_UNITTEST_DEBUG"))


def open_without_clobber(name, *args):
    """
    Try to open the given file with the given mode; if that filename exists,
    try "name.1", "name.2", etc. until we find an unused filename.
    """
    fd = None
    count = 1
    orig_name = name
    while fd is None:
        try:
            fd = os.open(name, os.O_CREAT | os.O_EXCL, 0o666)
        except OSError as err:
            if err.errno == errno.EEXIST:
                name = "%s.%i" % (orig_name, count)
                count += 1
            else:  # pragma: no cover
                raise IOError(err.errno, err.strerror, err.filename) from None
    fobj = open(name, *args)
    if fd != fobj.fileno():
        os.close(fd)
    return fobj


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
        log.setLevel(DEBUG)  # pragma: no cover


##################
# Option parsing #
##################

def _setup_root_parser():
    epilog = 'Try "bugzilla COMMAND --help" for command-specific help.'
    p = argparse.ArgumentParser(epilog=epilog)

    default_url = bugzilla.Bugzilla.get_rcfile_default_url()
    if not default_url:
        default_url = DEFAULT_BZ

    # General bugzilla connection options
    p.add_argument('--bugzilla', default=default_url,
            help="bugzilla URI. default: %s" % default_url)
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
    p.add_argument('--restrict-login', action="store_true",
                   help="The session (login token) will be restricted to "
                        "the current IP address.")

    p.add_argument('--ensure-logged-in', action="store_true",
        help="Raise an error if we aren't logged in to bugzilla. "
             "Consider using this if you are depending on "
             "cached credentials, to ensure that when they expire the "
             "tool errors, rather than subtly change output.")
    p.add_argument('--no-cache-credentials',
        action='store_false', default=True, dest='cache_credentials',
        help="Don't save any bugzilla cookies or tokens to disk, and "
             "don't use any pre-existing credentials.")

    p.add_argument('--cookiefile', default=None, help=argparse.SUPPRESS)
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
    outg.add_argument('--json', action='store_const', dest='output',
            const='json', help="output contents in json format")
    outg.add_argument("--includefield", action="append",
            help="Pass the field name to bugzilla include_fields list. "
                 "Only the fields passed to include_fields are returned "
                 "by the bugzilla server. "
                 "This can be specified multiple times.")
    outg.add_argument("--extrafield", action="append",
            help="Pass the field name to bugzilla extra_fields list. "
                 "When used with --json this can be used to request "
                 "bugzilla to return values for non-default fields. "
                 "This can be specified multiple times.")
    outg.add_argument("--excludefield", action="append",
            help="Pass the field name to bugzilla exclude_fields list. "
                 "When used with --json this can be used to request "
                 "bugzilla to not return values for a field. "
                 "This can be specified multiple times.")
    outg.add_argument('--raw', action='store_const', dest='output',
            const='raw', help="raw output of the bugzilla contents. This "
            "format is unstable and difficult to parse. Use --json instead.")
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
    if cmd_modify:
        p.add_argument("--minor-update", action="store_true",
                help="Request bugzilla to not send any "
                     "email about this change")

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
        help="Manually specify a bugzilla API field. FIELD is "
        "the raw name used by the bugzilla instance. For example, if your "
        "bugzilla instance has a custom field cf_my_field, do:\n"
        "  --field cf_my_field=VALUE")

    if not cmd_modify:
        _parser_add_output_options(rootp)


def _setup_action_new_parser(subparsers):
    description = ("Create a new bug report. "
        "--product, --component, --version, --summary, and --comment "
        "must be specified. "
        "Options that take multiple values accept comma separated lists, "
        "including --cc, --blocks, --dependson, --groups, and --keywords.")
    p = subparsers.add_parser("new", description=description)
    p.add_argument('--no-refresh', action='store_true',
                   help='Do not refresh bug after creating')

    _parser_add_bz_fields(p, "new")
    g = p.add_argument_group("'new' specific options")
    g.add_argument('--private', action='store_true', default=False,
        help='Mark new comment as private')


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
    p.add_argument('--active-versions', action="store_true",
            help='Only show active versions. Combine with --versions')



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
bugzilla attach --get=ATTACHID --getall=BUGID [--ignore-obsolete] [...]
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
    p.add_argument('--ignore-obsolete', action="store_true",
        help='Do not download attachments marked as obsolete.')
    p.add_argument('-l', '--comment', '--long_desc',
            help="Add comment with attachment")
    p.add_argument('--private', action='store_true', default=False,
        help='Mark new comment as private')


def _setup_action_login_parser(subparsers):
    usage = 'bugzilla login [--api-key] [username [password]]'
    description = """Log into bugzilla and save a login cookie or token.
Note: These tokens are short-lived, and future Bugzilla versions will no
longer support token authentication at all. Please use a
~/.config/python-bugzilla/bugzillarc file with an API key instead, or
use 'bugzilla login --api-key' and we will save it for you."""
    p = subparsers.add_parser("login", description=description, usage=usage)
    p.add_argument('--api-key', action='store_true', default=False,
                   help='Prompt for and save an API key into bugzillarc, '
                        'rather than prompt for username and password.')
    p.add_argument("pos_username", nargs="?", help="Optional username ",
                   metavar="username")
    p.add_argument("pos_password", nargs="?", help="Optional password ",
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

def _merge_field_opts(query, fields, parser):
    # Add any custom fields if specified
    for f in fields:
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
            # non-RESOLVED statuses
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
    if opt.output in ['raw', 'json']:
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

    kwopts = {}
    if opt.product:
        kwopts["product"] = opt.product
    if opt.component:
        kwopts["component"] = opt.component
    if opt.sub_component:
        kwopts["sub_component"] = opt.sub_component
    if opt.version:
        kwopts["version"] = opt.version
    if opt.reporter:
        kwopts["reporter"] = opt.reporter
    if opt.id:
        kwopts["bug_id"] = opt.id
    if opt.summary:
        kwopts["short_desc"] = opt.summary
    if opt.comment:
        kwopts["long_desc"] = opt.comment
    if opt.cc:
        kwopts["cc"] = opt.cc
    if opt.assigned_to:
        kwopts["assigned_to"] = opt.assigned_to
    if opt.qa_contact:
        kwopts["qa_contact"] = opt.qa_contact
    if opt.status:
        kwopts["status"] = opt.status
    if opt.blocked:
        kwopts["blocked"] = opt.blocked
    if opt.dependson:
        kwopts["dependson"] = opt.dependson
    if opt.keywords:
        kwopts["keywords"] = opt.keywords
    if opt.keywords_type:
        kwopts["keywords_type"] = opt.keywords_type
    if opt.url:
        kwopts["url"] = opt.url
    if opt.url_type:
        kwopts["url_type"] = opt.url_type
    if opt.whiteboard:
        kwopts["status_whiteboard"] = opt.whiteboard
    if opt.status_whiteboard_type:
        kwopts["status_whiteboard_type"] = opt.status_whiteboard_type
    if opt.fixed_in:
        kwopts["fixed_in"] = opt.fixed_in
    if opt.fixed_in_type:
        kwopts["fixed_in_type"] = opt.fixed_in_type
    if opt.flag:
        kwopts["flag"] = opt.flag
    if opt.alias:
        kwopts["alias"] = opt.alias
    if opt.qa_whiteboard:
        kwopts["qa_whiteboard"] = opt.qa_whiteboard
    if opt.devel_whiteboard:
        kwopts["devel_whiteboard"] = opt.devel_whiteboard
    if opt.severity:
        kwopts["bug_severity"] = opt.severity
    if opt.priority:
        kwopts["priority"] = opt.priority
    if opt.target_release:
        kwopts["target_release"] = opt.target_release
    if opt.target_milestone:
        kwopts["target_milestone"] = opt.target_milestone
    if opt.emailtype:
        kwopts["emailtype"] = opt.emailtype
    if include_fields:
        kwopts["include_fields"] = include_fields
    if opt.quicksearch:
        kwopts["quicksearch"] = opt.quicksearch
    if opt.savedsearch:
        kwopts["savedsearch"] = opt.savedsearch
    if opt.savedsearch_sharer_id:
        kwopts["savedsearch_sharer_id"] = opt.savedsearch_sharer_id
    if opt.tags:
        kwopts["tags"] = opt.tags

    built_query = bz.build_query(**kwopts)
    if opt.fields:
        _merge_field_opts(built_query, opt.fields, parser)

    built_query.update(q)
    q = built_query

    if not q:  # pragma: no cover
        parser.error("'query' command requires additional arguments")
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
    fastcomponents = (opt.components and not opt.active_components)

    include_fields = ["name", "id"]
    if opt.components or opt.component_owners:
        include_fields += ["components.name"]
        if opt.component_owners:
            include_fields += ["components.default_assigned_to"]
        if opt.active_components:
            include_fields += ["components.is_active"]

    if opt.versions:
        include_fields += ["versions"]

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
            if not opt.active_versions or v["is_active"]:
                print(str(v["name"] or ''))

    elif opt.component_owners:
        details = bz.getcomponentsdetails(productname)
        for c in sorted(_filter_components(details)):
            print("%s: %s" % (c, details[c]['default_assigned_to']))


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

    else:  # pragma: no cover
        raise RuntimeError("Unknown output type '%s'" % output)

    return fmt


def _xmlrpc_converter(obj):
    if "DateTime" in str(obj.__class__):
        # xmlrpc DateTime object. Convert to date format that
        # bugzilla REST API outputs
        dobj = datetime.datetime.strptime(str(obj), '%Y%m%dT%H:%M:%S')
        return dobj.isoformat() + "Z"
    if "Binary" in str(obj.__class__):
        # xmlrpc Binary object. Convert to base64
        return base64.b64encode(obj.data).decode("utf-8")
    raise RuntimeError(
        "Unexpected JSON conversion class=%s" % obj.__class__)


def _format_output_json(buglist):
    out = {"bugs": [b.get_raw_data() for b in buglist]}
    s = json.dumps(out, default=_xmlrpc_converter, indent=2, sort_keys=True)
    print(s)


def _format_output_raw(buglist):
    for b in buglist:
        print("Bugzilla %s: " % b.bug_id)
        SKIP_NAMES = ["bugzilla"]
        for attrname in sorted(b.__dict__):
            if attrname in SKIP_NAMES:
                continue
            if attrname.startswith("_"):
                continue
            print("ATTRIBUTE[%s]: %s" % (attrname, b.__dict__[attrname]))
        print("\n\n")


def _bug_field_repl_cb(bz, b, matchobj):
    # whiteboard and flag allow doing
    #   %{whiteboard:devel} and %{flag:needinfo}
    # That's what 'rest' matches
    (fieldname, rest) = matchobj.groups()

    if fieldname == "whiteboard" and rest:
        fieldname = rest + "_" + fieldname

    if fieldname == "flag" and rest:
        val = b.get_flag_status(rest)

    elif fieldname in ["flags", "flags_requestee"]:
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
                    if (cb.find("CVE") != -1 and
                        cb.strip() not in cves):
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
    val = ','.join([str(v or '') for v in vallist])

    return val


def _format_output(bz, opt, buglist):
    if opt.output in ['raw', 'json']:
        include_fields = None
        exclude_fields = None
        extra_fields = None

        if opt.includefield:
            include_fields = opt.includefield
        if opt.excludefield:
            exclude_fields = opt.excludefield
        if opt.extrafield:
            extra_fields = opt.extrafield

        buglist = bz.getbugs([b.bug_id for b in buglist],
                include_fields=include_fields,
                exclude_fields=exclude_fields,
                extra_fields=extra_fields)
        if opt.output == 'json':
            _format_output_json(buglist)
        if opt.output == 'raw':
            _format_output_raw(buglist)
        return

    for b in buglist:
        # pylint: disable=cell-var-from-loop
        def cb(matchobj):
            return _bug_field_repl_cb(bz, b, matchobj)
        print(format_field_re.sub(cb, opt.outputformat))


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

    kwopts = {}
    if opt.blocked:
        kwopts["blocks"] = parse_multi(opt.blocked)
    if opt.cc:
        kwopts["cc"] = parse_multi(opt.cc)
    if opt.component:
        kwopts["component"] = opt.component
    if opt.dependson:
        kwopts["depends_on"] = parse_multi(opt.dependson)
    if opt.comment:
        kwopts["description"] = opt.comment
    if opt.groups:
        kwopts["groups"] = parse_multi(opt.groups)
    if opt.keywords:
        kwopts["keywords"] = parse_multi(opt.keywords)
    if opt.os:
        kwopts["op_sys"] = opt.os
    if opt.arch:
        kwopts["platform"] = opt.arch
    if opt.priority:
        kwopts["priority"] = opt.priority
    if opt.product:
        kwopts["product"] = opt.product
    if opt.severity:
        kwopts["severity"] = opt.severity
    if opt.summary:
        kwopts["summary"] = opt.summary
    if opt.url:
        kwopts["url"] = opt.url
    if opt.version:
        kwopts["version"] = opt.version
    if opt.assigned_to:
        kwopts["assigned_to"] = opt.assigned_to
    if opt.qa_contact:
        kwopts["qa_contact"] = opt.qa_contact
    if opt.sub_component:
        kwopts["sub_component"] = opt.sub_component
    if opt.alias:
        kwopts["alias"] = opt.alias
    if opt.comment_tag:
        kwopts["comment_tags"] = opt.comment_tag
    if opt.private:
        kwopts["comment_private"] = opt.private

    ret = bz.build_createbug(**kwopts)
    if opt.fields:
        _merge_field_opts(ret, opt.fields, parser)

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

    update_opts = {}

    if opt.assigned_to:
        update_opts["assigned_to"] = opt.assigned_to
    if opt.comment:
        update_opts["comment"] = opt.comment
    if opt.private:
        update_opts["comment_private"] = opt.private
    if opt.component:
        update_opts["component"] = opt.component
    if opt.product:
        update_opts["product"] = opt.product
    if add_blk:
        update_opts["blocks_add"] = add_blk
    if rm_blk:
        update_opts["blocks_remove"] = rm_blk
    if set_blk is not None:
        update_opts["blocks_set"] = set_blk
    if opt.url:
        update_opts["url"] = opt.url
    if add_cc:
        update_opts["cc_add"] = add_cc
    if rm_cc:
        update_opts["cc_remove"] = rm_cc
    if add_deps:
        update_opts["depends_on_add"] = add_deps
    if rm_deps:
        update_opts["depends_on_remove"] = rm_deps
    if set_deps is not None:
        update_opts["depends_on_set"] = set_deps
    if add_groups:
        update_opts["groups_add"] = add_groups
    if rm_groups:
        update_opts["groups_remove"] = rm_groups
    if add_key:
        update_opts["keywords_add"] = add_key
    if rm_key:
        update_opts["keywords_remove"] = rm_key
    if set_key is not None:
        update_opts["keywords_set"] = set_key
    if opt.os:
        update_opts["op_sys"] = opt.os
    if opt.arch:
        update_opts["platform"] = opt.arch
    if opt.priority:
        update_opts["priority"] = opt.priority
    if opt.qa_contact:
        update_opts["qa_contact"] = opt.qa_contact
    if opt.severity:
        update_opts["severity"] = opt.severity
    if status:
        update_opts["status"] = status
    if opt.summary:
        update_opts["summary"] = opt.summary
    if opt.version:
        update_opts["version"] = opt.version
    if opt.reset_assignee:
        update_opts["reset_assigned_to"] = opt.reset_assignee
    if opt.reset_qa_contact:
        update_opts["reset_qa_contact"] = opt.reset_qa_contact
    if opt.close:
        update_opts["resolution"] = opt.close
    if opt.target_release:
        update_opts["target_release"] = opt.target_release
    if opt.target_milestone:
        update_opts["target_milestone"] = opt.target_milestone
    if opt.dupeid:
        update_opts["dupe_of"] = opt.dupeid
    if opt.fixed_in:
        update_opts["fixed_in"] = opt.fixed_in
    if set_wb and set_wb[0]:
        update_opts["whiteboard"] = set_wb and set_wb[0]
    if set_devwb and set_devwb[0]:
        update_opts["devel_whiteboard"] = set_devwb and set_devwb[0]
    if set_intwb and set_intwb[0]:
        update_opts["internal_whiteboard"] = set_intwb and set_intwb[0]
    if set_qawb and set_qawb[0]:
        update_opts["qa_whiteboard"] = set_qawb and set_qawb[0]
    if opt.sub_component:
        update_opts["sub_component"] = opt.sub_component
    if opt.alias:
        update_opts["alias"] = opt.alias
    if flags:
        update_opts["flags"] = flags
    if opt.comment_tag:
        update_opts["comment_tags"] = opt.comment_tag
    if opt.minor_update:
        update_opts["minor_update"] = opt.minor_update

    update = bz.build_update(**update_opts)

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

    if opt.fields:
        _merge_field_opts(update, opt.fields, parser)

    log.debug("update bug dict=%s", update)
    log.debug("update whiteboard dict=%s", wbmap)

    if not any([update, wbmap, add_tags, rm_tags]):
        parser.error("'modify' command requires additional arguments")

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
    # here. This is a bit weird for traditional bugzilla API
    log.debug("Adjusting whiteboard fields one by one")
    for bug in bz.getbugs(bugid_list):
        update_kwargs = {}
        for wbkey, (add_list, rm_list) in wbmap.items():
            bugval = getattr(bug, wbkey) or ""
            for tag in add_list:
                if bugval:
                    bugval += " "
                bugval += tag

            for tag in rm_list:
                bugsplit = bugval.split()
                for t in bugsplit[:]:
                    if t == tag:
                        bugsplit.remove(t)
                bugval = " ".join(bugsplit)

            update_kwargs[wbkey] = bugval

        bz.update_bugs([bug.id], bz.build_update(**update_kwargs))


def _do_get_attach(bz, opt):
    data = {}

    def _process_attachment_data(_attlist):
        for _att in _attlist:
            data[_att["id"]] = _att

    if opt.getall:
        for attlist in bz.get_attachments(opt.getall, None)["bugs"].values():
            _process_attachment_data(attlist)
    if opt.get:
        _process_attachment_data(
            bz.get_attachments(None, opt.get)["attachments"].values())

    for attdata in data.values():
        is_obsolete = attdata.get("is_obsolete", None) == 1
        if opt.ignore_obsolete and is_obsolete:
            continue

        att = bz.openattachment_data(attdata)
        outfile = open_without_clobber(att.name, "wb")
        data = att.read(4096)
        while data:
            outfile.write(data)
            data = att.read(4096)
        print("Wrote %s" % outfile.name)


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
    if opt.private:
        kwargs["is_private"] = True
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
    use_creds = False
    if opt.cache_credentials:
        cookiefile = opt.cookiefile or -1
        tokenfile = opt.tokenfile or -1
        use_creds = True

    return bugzilla.Bugzilla(
        url=opt.bugzilla,
        cookiefile=cookiefile,
        tokenfile=tokenfile,
        sslverify=opt.sslverify,
        use_creds=use_creds,
        cert=opt.cert)


def _handle_login(opt, action, bz):
    """
    Handle all login related bits
    """
    is_login_command = (action == 'login')

    do_interactive_login = (is_login_command or
        opt.login or opt.username or opt.password)
    username = getattr(opt, "pos_username", None) or opt.username
    password = getattr(opt, "pos_password", None) or opt.password
    use_key = getattr(opt, "api_key", False)

    try:
        if use_key:
            bz.interactive_save_api_key()
        elif do_interactive_login:
            if bz.api_key:
                print("You already have an API key configured for %s" % bz.url)
                print("There is no need to cache a login token. Exiting.")
                sys.exit(0)
            print("Logging into %s" % urllib.parse.urlparse(bz.url)[1])
            bz.interactive_login(username, password,
                    restrict_login=opt.restrict_login)
    except bugzilla.BugzillaError as e:
        print(str(e))
        sys.exit(1)

    if opt.ensure_logged_in and not bz.logged_in:
        print("--ensure-logged-in passed but you aren't logged in to %s" %
            bz.url)
        sys.exit(1)

    if is_login_command:
        sys.exit(0)


def _main(unittest_bz_instance):
    parser = setup_parser()
    opt = parser.parse_args()
    action = opt.command
    setup_logging(opt.debug, opt.verbose)

    log.debug("Launched with command line: %s", " ".join(sys.argv))
    log.debug("Bugzilla module: %s", bugzilla)

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
        if not opt.outputformat and opt.output not in ['raw', 'json', None]:
            opt.outputformat = _convert_to_outputformat(opt.output)

    buglist = []
    if action == 'info':
        _do_info(bz, opt)

    elif action == 'query':
        buglist = _do_query(bz, opt, parser)

    elif action == 'new':
        buglist = _do_new(bz, opt, parser)

    elif action == 'attach':
        if opt.get or opt.getall:
            if opt.ids:
                parser.error("Bug IDs '%s' not used for "
                    "getting attachments" % opt.ids)
            _do_get_attach(bz, opt)
        else:
            _do_set_attach(bz, opt, parser)

    elif action == 'modify':
        _do_modify(bz, parser, opt)
    else:  # pragma: no cover
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
    except KeyboardInterrupt:
        print("\nExited at user request.")
        sys.exit(1)
    except (xmlrpc.client.Fault, bugzilla.BugzillaError) as e:
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
            requests.exceptions.InvalidURL,
            xmlrpc.client.ProtocolError) as e:
        print("\nConnection lost/failed: %s" % str(e))
        sys.exit(2)


def cli():
    main()
