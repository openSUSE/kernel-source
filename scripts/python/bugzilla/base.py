# base.py - the base classes etc. for a Python interface to bugzilla
#
# Copyright (C) 2007, 2008, 2009, 2010 Red Hat Inc.
# Author: Will Woods <wwoods@redhat.com>
#
# This work is licensed under the GNU GPLv2 or later.
# See the COPYING file in the top-level directory.

import collections
import getpass
import locale
from logging import getLogger
import mimetypes
import os
import sys
import urllib.parse

from io import BytesIO

from ._authfiles import _BugzillaRCFile, _BugzillaTokenCache
from .apiversion import __version__
from ._backendrest import _BackendREST
from ._backendxmlrpc import _BackendXMLRPC
from .bug import Bug, Group, User
from .exceptions import BugzillaError
from ._rhconverters import _RHBugzillaConverters
from ._session import _BugzillaSession
from ._util import listify


log = getLogger(__name__)


def _nested_update(d, u):
    # Helper for nested dict update()
    for k, v in list(u.items()):
        if isinstance(v, collections.abc.Mapping):
            d[k] = _nested_update(d.get(k, {}), v)
        else:
            d[k] = v
    return d


class _FieldAlias(object):
    """
    Track API attribute names that differ from what we expose in users.

    For example, originally 'short_desc' was the name of the property that
    maps to 'summary' on modern bugzilla. We want pre-existing API users
    to be able to continue to use Bug.short_desc, and
    query({"short_desc": "foo"}). This class tracks that mapping.

    @oldname: The old attribute name
    @newname: The modern attribute name
    @is_api: If True, use this mapping for values sent to the xmlrpc API
        (like the query example)
    @is_bug: If True, use this mapping for Bug attribute names.
    """
    def __init__(self, newname, oldname, is_api=True, is_bug=True):
        self.newname = newname
        self.oldname = oldname
        self.is_api = is_api
        self.is_bug = is_bug


class _BugzillaAPICache(object):
    """
    Helper class that holds cached API results for things like products,
    components, etc.
    """
    def __init__(self):
        self.products = []
        self.component_names = {}
        self.bugfields = []
        self.version_raw = None
        self.version_parsed = (0, 0)


class Bugzilla(object):
    """
    The main API object. Connects to a bugzilla instance over XMLRPC, and
    provides wrapper functions to simplify dealing with API calls.

    The most common invocation here will just be with just a URL:

        bzapi = Bugzilla("http://bugzilla.example.com")

    If you have previously logged into that URL, and have cached login
    tokens, you will automatically be logged in. Otherwise to
    log in, you can either pass auth options to __init__, or call a login
    helper like interactive_login().

    If you are not logged in, you won't be able to access restricted data like
    user email, or perform write actions like bug create/update. But simple
    querys will work correctly.

    If you are unsure if you are logged in, you can check the .logged_in
    property.

    Another way to specify auth credentials is via a 'bugzillarc' file.
    See readconfig() documentation for details.
    """
    @staticmethod
    def url_to_query(url):
        """
        Given a big huge bugzilla query URL, returns a query dict that can
        be passed along to the Bugzilla.query() method.
        """
        q = {}

        # pylint: disable=unpacking-non-sequence
        (ignore1, ignore2, path,
         ignore, query, ignore3) = urllib.parse.urlparse(url)

        base = os.path.basename(path)
        if base not in ('buglist.cgi', 'query.cgi'):
            return {}

        for (k, v) in urllib.parse.parse_qsl(query):
            if k not in q:
                q[k] = v
            elif isinstance(q[k], list):
                q[k].append(v)
            else:
                oldv = q[k]
                q[k] = [oldv, v]

        # Handle saved searches
        if base == "buglist.cgi" and "namedcmd" in q and "sharer_id" in q:
            q = {
                "sharer_id": q["sharer_id"],
                "savedsearch": q["namedcmd"],
            }

        return q

    @staticmethod
    def fix_url(url, force_rest=False):
        """
        Turn passed url into a bugzilla XMLRPC web url

        :param force_rest: If True, generate a REST API url
        """
        (scheme, netloc, path,
         params, query, fragment) = urllib.parse.urlparse(url)
        if not scheme:
            scheme = 'https'

        if path and not netloc:
            netloc = path.split("/", 1)[0]
            path = "/".join(path.split("/")[1:]) or None

        if not path:
            path = 'xmlrpc.cgi'
            if force_rest:
                path = "rest/"

        newurl = urllib.parse.urlunparse(
            (scheme, netloc, path, params, query, fragment))
        return newurl

    @staticmethod
    def get_rcfile_default_url():
        """
        Helper to check all the default bugzillarc file paths for
        a [DEFAULT] url=X section, and if found, return it.
        """
        configpaths = _BugzillaRCFile.get_default_configpaths()
        rcfile = _BugzillaRCFile()
        rcfile.set_configpaths(configpaths)
        return rcfile.get_default_url()


    def __init__(self, url=-1, user=None, password=None, cookiefile=-1,
                 sslverify=True, tokenfile=-1, use_creds=True, api_key=None,
                 cert=None, configpaths=-1,
                 force_rest=False, force_xmlrpc=False, requests_session=None):
        """
        :param url: The bugzilla instance URL, which we will connect
            to immediately. Most users will want to specify this at
            __init__ time, but you can defer connecting by passing
            url=None and calling connect(URL) manually
        :param user: optional username to connect with
        :param password: optional password for the connecting user
        :param cert: optional certificate file for client side certificate
            authentication
        :param cookiefile: Deprecated, raises an error if not -1 or None
        :param sslverify: Set this to False to skip SSL hostname and CA
            validation checks, like out of date certificate
        :param tokenfile: Location to cache the API login token so youi
            don't have to keep specifying username/password.
            If -1, use the default path. If None, don't use
            or save any tokenfile.
        :param use_creds: If False, this disables tokenfile
            and configpaths by default. This is a convenience option to
            unset those values at init time. If those values are later
            changed, they may be used for future operations.
        :param sslverify: Maps to 'requests' sslverify parameter. Set to
            False to disable SSL verification, but it can also be a path
            to file or directory for custom certs.
        :param api_key: A bugzilla5+ API key
        :param configpaths: A list of possible bugzillarc locations.
        :param force_rest: Force use of the REST API
        :param force_xmlrpc: Force use of the XMLRPC API. If neither force_X
            parameter are specified, heuristics will be used to determine
            which API to use, with XMLRPC preferred for back compatability.
        :param requests_session: An optional requests.Session object the
            API will use to contact the remote bugzilla instance. This
            way the API user can set up whatever auth bits they may need.
        """
        if url == -1:
            raise TypeError("Specify a valid bugzilla url, or pass url=None")

        # Settings the user might want to tweak
        self.user = user or ''
        self.password = password or ''
        self.api_key = api_key
        self.cert = cert or None
        self.url = ''

        self._backend = None
        self._session = None
        self._user_requests_session = requests_session
        self._sslverify = sslverify
        self._cache = _BugzillaAPICache()
        self._bug_autorefresh = False
        self._is_redhat_bugzilla = False

        self._rcfile = _BugzillaRCFile()
        self._tokencache = _BugzillaTokenCache()

        self._force_rest = force_rest
        self._force_xmlrpc = force_xmlrpc

        if cookiefile not in [None, -1]:
            raise TypeError("cookiefile is deprecated, don't pass any value.")

        if not use_creds:
            tokenfile = None
            configpaths = []

        if tokenfile == -1:
            tokenfile = self._tokencache.get_default_path()
        if configpaths == -1:
            configpaths = _BugzillaRCFile.get_default_configpaths()

        self._settokenfile(tokenfile)
        self._setconfigpath(configpaths)

        if url:
            self.connect(url)

    def _detect_is_redhat_bugzilla(self):
        if self._is_redhat_bugzilla:
            return True

        match = ".redhat.com"
        if match in self.url:
            log.info("Using RHBugzilla for URL containing %s", match)
            return True

        return False

    def _init_class_from_url(self):
        """
        Detect if we should use RHBugzilla class, and if so, set it
        """
        from .oldclasses import RHBugzilla  # pylint: disable=cyclic-import

        if not self._detect_is_redhat_bugzilla():
            return

        self._is_redhat_bugzilla = True
        if self.__class__ == Bugzilla:
            # Overriding the class doesn't have any functional effect,
            # but we continue to do it for API back compat incase anyone
            # is doing any class comparison. We should drop this in the future
            self.__class__ = RHBugzilla

    def _get_field_aliases(self):
        # List of field aliases. Maps old style RHBZ parameter
        # names to actual upstream values. Used for createbug() and
        # query include_fields at least.
        ret = []

        def _add(*args, **kwargs):
            ret.append(_FieldAlias(*args, **kwargs))

        def _add_both(newname, origname):
            _add(newname, origname, is_api=False)
            _add(origname, newname, is_bug=False)

        _add('summary', 'short_desc')
        _add('description', 'comment')
        _add('platform', 'rep_platform')
        _add('severity', 'bug_severity')
        _add('status', 'bug_status')
        _add('id', 'bug_id')
        _add('blocks', 'blockedby')
        _add('blocks', 'blocked')
        _add('depends_on', 'dependson')
        _add('creator', 'reporter')
        _add('url', 'bug_file_loc')
        _add('dupe_of', 'dupe_id')
        _add('dupe_of', 'dup_id')
        _add('comments', 'longdescs')
        _add('creation_time', 'opendate')
        _add('creation_time', 'creation_ts')
        _add('whiteboard', 'status_whiteboard')
        _add('last_change_time', 'delta_ts')

        if self._is_redhat_bugzilla:
            _add_both('fixed_in', 'cf_fixed_in')
            _add_both('qa_whiteboard', 'cf_qa_whiteboard')
            _add_both('devel_whiteboard', 'cf_devel_whiteboard')
            _add_both('internal_whiteboard', 'cf_internal_whiteboard')

            _add('component', 'components', is_bug=False)
            _add('version', 'versions', is_bug=False)
            # Yes, sub_components is the field name the API expects
            _add('sub_components', 'sub_component', is_bug=False)
            # flags format isn't exactly the same but it's the closest approx
            _add('flags', 'flag_types')

        return ret

    def _get_user_agent(self):
        return 'python-bugzilla/%s' % __version__
    user_agent = property(_get_user_agent)

    @property
    def bz_ver_major(self):
        return self._cache.version_parsed[0]

    @property
    def bz_ver_minor(self):
        return self._cache.version_parsed[1]


    ###################
    # Private helpers #
    ###################

    def _get_version(self):
        """
        Return version number as a float
        """
        return float("%d.%d" % (self.bz_ver_major, self.bz_ver_minor))

    def _get_bug_aliases(self):
        return [(f.newname, f.oldname)
                for f in self._get_field_aliases() if f.is_bug]

    def _get_api_aliases(self):
        return [(f.newname, f.oldname)
                for f in self._get_field_aliases() if f.is_api]


    #################
    # Auth handling #
    #################

    def _getcookiefile(self):
        return None
    cookiefile = property(_getcookiefile)

    def _gettokenfile(self):
        return self._tokencache.get_filename()
    def _settokenfile(self, filename):
        self._tokencache.set_filename(filename)
    def _deltokenfile(self):
        self._settokenfile(None)
    tokenfile = property(_gettokenfile, _settokenfile, _deltokenfile)

    def _getconfigpath(self):
        return self._rcfile.get_configpaths()
    def _setconfigpath(self, configpaths):
        return self._rcfile.set_configpaths(configpaths)
    def _delconfigpath(self):
        return self._rcfile.set_configpaths(None)
    configpath = property(_getconfigpath, _setconfigpath, _delconfigpath)


    #############################
    # Login/connection handling #
    #############################

    def readconfig(self, configpath=None, overwrite=True):
        """
        :param configpath: Optional bugzillarc path to read, instead of
            the default list.

        This function is called automatically from Bugzilla connect(), which
        is called at __init__ if a URL is passed. Calling it manually is
        just for passing in a non-standard configpath.

        The locations for the bugzillarc file are preferred in this order:

            ~/.config/python-bugzilla/bugzillarc
            ~/.bugzillarc
            /etc/bugzillarc

        It has content like:
          [bugzilla.yoursite.com]
          user = username
          password = password
        Or
          [bugzilla.yoursite.com]
          api_key = key

        The file can have multiple sections for different bugzilla instances.
        A 'url' field in the [DEFAULT] section can be used to set a default
        URL for the bugzilla command line tool.

        Be sure to set appropriate permissions on bugzillarc if you choose to
        store your password in it!

        :param overwrite: If True, bugzillarc will clobber any already
            set self.user/password/api_key/cert value.
        """
        if configpath:
            self._setconfigpath(configpath)
        data = self._rcfile.parse(self.url)

        for key, val in data.items():
            if key == "api_key" and (overwrite or not self.api_key):
                log.debug("bugzillarc: setting api_key")
                self.api_key = val
            elif key == "user" and (overwrite or not self.user):
                log.debug("bugzillarc: setting user=%s", val)
                self.user = val
            elif key == "password" and (overwrite or not self.password):
                log.debug("bugzillarc: setting password")
                self.password = val
            elif key == "cert" and (overwrite or not self.cert):
                log.debug("bugzillarc: setting cert")
                self.cert = val
            else:
                log.debug("bugzillarc: unknown key=%s", key)

    def _set_bz_version(self, version):
        self._cache.version_raw = version
        try:
            major, minor = [int(i) for i in version.split(".")[0:2]]
        except Exception:
            log.debug("version doesn't match expected format X.Y.Z, "
                    "assuming 5.0", exc_info=True)
            major = 5
            minor = 0
        self._cache.version_parsed = (major, minor)

    def _get_backend_class(self, url):  # pragma: no cover
        # This is a hook for the test suite to do some mock hackery
        if self._force_rest and self._force_xmlrpc:
            raise BugzillaError(
                "Cannot specify both force_rest and force_xmlrpc")

        xmlurl = self.fix_url(url)
        if self._force_xmlrpc:
            return _BackendXMLRPC, xmlurl

        resturl = self.fix_url(url, force_rest=self._force_rest)
        if self._force_rest:
            return _BackendREST, resturl

        # Simple heuristic if the original url has a path in it
        if "/xmlrpc" in url:
            return _BackendXMLRPC, xmlurl
        if "/rest" in url:
            return _BackendREST, resturl

        # We were passed something like bugzilla.example.com but we
        # aren't sure which method to use, try probing
        if _BackendXMLRPC.probe(xmlurl):
            return _BackendXMLRPC, xmlurl
        if _BackendREST.probe(resturl):
            return _BackendREST, resturl

        # Otherwise fallback to XMLRPC default and let it fail
        return _BackendXMLRPC, xmlurl

    def connect(self, url=None):
        """
        Connect to the bugzilla instance with the given url. This is
        called by __init__ if a URL is passed. Or it can be called manually
        at any time with a passed URL.

        This will also read any available config files (see readconfig()),
        which may set 'user' and 'password', and others.

        If 'user' and 'password' are both set, we'll run login(). Otherwise
        you'll have to login() yourself before some methods will work.
        """
        if self._session:
            self.disconnect()

        url = url or self.url
        backendclass, newurl = self._get_backend_class(url)
        if url != newurl:
            log.debug("Converted url=%s to fixed url=%s", url, newurl)
        self.url = newurl
        log.debug("Connecting with URL %s", self.url)

        # we've changed URLs - reload config
        self.readconfig(overwrite=False)

        # Detect if connecting to redhat bugzilla
        self._init_class_from_url()

        self._session = _BugzillaSession(self.url, self.user_agent,
                sslverify=self._sslverify,
                cert=self.cert,
                tokencache=self._tokencache,
                api_key=self.api_key,
                is_redhat_bugzilla=self._is_redhat_bugzilla,
                requests_session=self._user_requests_session)
        self._backend = backendclass(self.url, self._session)

        if (self.user and self.password):
            log.info("user and password present - doing login()")
            self.login()

        if self.api_key:
            log.debug("using API key")

        version = self._backend.bugzilla_version()["version"]
        log.debug("Bugzilla version string: %s", version)
        self._set_bz_version(version)


    @property
    def _proxy(self):
        """
        Return an xmlrpc ServerProxy instance that will work seamlessly
        with bugzilla

        Some apps have historically accessed _proxy directly, like
        fedora infrastrucutre pieces. So we consider it part of the API
        """
        return self._backend.get_xmlrpc_proxy()

    def is_xmlrpc(self):
        """
        :returns: True if using the XMLRPC API
        """
        return self._backend.is_xmlrpc()

    def is_rest(self):
        """
        :returns: True if using the REST API
        """
        return self._backend.is_rest()

    def get_requests_session(self):
        """
        Give API users access to the Requests.session object we use for
        talking to the remote bugzilla instance.

        :returns: The Requests.session object backing the open connection.
        """
        return self._session.get_requests_session()

    def disconnect(self):
        """
        Disconnect from the given bugzilla instance.
        """
        self._backend = None
        self._session = None
        self._cache = _BugzillaAPICache()

    def login(self, user=None, password=None, restrict_login=None):
        """
        Attempt to log in using the given username and password. Subsequent
        method calls will use this username and password. Returns False if
        login fails, otherwise returns some kind of login info - typically
        either a numeric userid, or a dict of user info.

        If user is not set, the value of Bugzilla.user will be used. If *that*
        is not set, ValueError will be raised. If login fails, BugzillaError
        will be raised.

        The login session can be restricted to current user IP address
        with restrict_login argument. (Bugzilla 4.4+)

        This method will be called implicitly at the end of connect() if user
        and password are both set. So under most circumstances you won't need
        to call this yourself.
        """
        if self.api_key:
            raise ValueError("cannot login when using an API key")

        if user:
            self.user = user
        if password:
            self.password = password

        if not self.user:
            raise ValueError("missing username")
        if not self.password:
            raise ValueError("missing password")

        payload = {"login": self.user}
        if restrict_login:
            payload['restrict_login'] = True
        log.debug("logging in with options %s", str(payload))
        payload['password'] = self.password

        try:
            ret = self._backend.user_login(payload)
            self.password = ''
            log.info("login succeeded for user=%s", self.user)
            if "token" in ret:
                self._tokencache.set_value(self.url, ret["token"])
            return ret
        except Exception as e:
            log.debug("Login exception: %s", str(e), exc_info=True)
            raise BugzillaError("Login failed: %s" %
                    BugzillaError.get_bugzilla_error_string(e)) from None

    def interactive_save_api_key(self):
        """
        Helper method to interactively ask for an API key, verify it
        is valid, and save it to a bugzillarc file referenced via
        self.configpaths
        """
        sys.stdout.write('API Key: ')
        sys.stdout.flush()
        api_key = sys.stdin.readline().strip()

        self.disconnect()
        self.api_key = api_key

        log.info('Checking API key... ')
        self.connect()

        if not self.logged_in:  # pragma: no cover
            raise BugzillaError("Login with API_KEY failed")
        log.info('API Key accepted')

        wrote_filename = self._rcfile.save_api_key(self.url, self.api_key)
        log.info("API key written to filename=%s", wrote_filename)

        msg = "Login successful."
        if wrote_filename:
            msg += " API key written to %s" % wrote_filename
        print(msg)

    def interactive_login(self, user=None, password=None, force=False,
                          restrict_login=None):
        """
        Helper method to handle login for this bugzilla instance.

        :param user: bugzilla username. If not specified, prompt for it.
        :param password: bugzilla password. If not specified, prompt for it.
        :param force: Unused
        :param restrict_login: restricts session to IP address
        """
        ignore = force
        log.debug('Calling interactive_login')

        if not user:
            sys.stdout.write('Bugzilla Username: ')
            sys.stdout.flush()
            user = sys.stdin.readline().strip()
        if not password:
            password = getpass.getpass('Bugzilla Password: ')

        log.info('Logging in... ')
        out = self.login(user, password, restrict_login)
        msg = "Login successful."
        if "token" not in out:
            msg += " However no token was returned."
        else:
            if not self.tokenfile:
                msg += " Token not saved to disk."
            else:
                msg += " Token cache saved to %s" % self.tokenfile
            if self._get_version() >= 5.0:
                msg += "\nToken usage is deprecated. "
                msg += "Consider using bugzilla API keys instead. "
                msg += "See `man bugzilla` for more details."
        print(msg)

    def logout(self):
        """
        Log out of bugzilla. Drops server connection and user info, and
        destroys authentication cache
        """
        self._backend.user_logout()
        self.disconnect()
        self.user = ''
        self.password = ''

    @property
    def logged_in(self):
        """
        This is True if this instance is logged in else False.

        We test if this session is authenticated by calling the User.get()
        XMLRPC method with ids set. Logged-out users cannot pass the 'ids'
        parameter and will result in a 505 error. If we tried to login with a
        token, but the token was incorrect or expired, the server returns a
        32000 error.

        For Bugzilla 5 and later, a new method, User.valid_login is available
        to test the validity of the token. However, this will require that the
        username be cached along with the token in order to work effectively in
        all scenarios and is not currently used. For more information, refer to
        the following url.

        http://bugzilla.readthedocs.org/en/latest/api/core/v1/user.html#valid-login
        """
        try:
            self._backend.user_get({"ids": [1]})
            return True
        except Exception as e:
            code = BugzillaError.get_bugzilla_error_code(e)
            if code in [505, 32000]:
                return False
            raise e


    ######################
    # Bugfields querying #
    ######################

    def getbugfields(self, force_refresh=False, names=None):
        """
        Calls getBugFields, which returns a list of fields in each bug
        for this bugzilla instance. This can be used to set the list of attrs
        on the Bug object.

        :param force_refresh: If True, overwrite the bugfield cache
            with these newly checked values.
        :param names: Only check for the passed bug field names
        """
        def _fieldnames():
            data = {"include_fields": ["name"]}
            if names:
                data["names"] = names
            r = self._backend.bug_fields(data)
            return [f['name'] for f in r['fields']]

        if force_refresh or not self._cache.bugfields:
            log.debug("Refreshing bugfields")
            self._cache.bugfields = _fieldnames()
            self._cache.bugfields.sort()
            log.debug("bugfields = %s", self._cache.bugfields)

        return self._cache.bugfields
    bugfields = property(fget=lambda self: self.getbugfields(),
                         fdel=lambda self: setattr(self, '_bugfields', None))


    ####################
    # Product querying #
    ####################

    def product_get(self, ids=None, names=None,
                    include_fields=None, exclude_fields=None,
                    ptype=None):
        """
        Raw wrapper around Product.get
        https://bugzilla.readthedocs.io/en/latest/api/core/v1/product.html#get-product

        This does not perform any caching like other product API calls.
        If ids, names, or ptype is not specified, we default to
        ptype=accessible for historical reasons

        @ids: List of product IDs to lookup
        @names: List of product names to lookup
        @ptype: Either 'accessible', 'selectable', or 'enterable'. If
            specified, we return data for all those
        @include_fields: Only include these fields in the output
        @exclude_fields: Do not include these fields in the output
        """
        if ids is None and names is None and ptype is None:
            ptype = "accessible"

        if ptype:
            raw = None
            if ptype == "accessible":
                raw = self._backend.product_get_accessible()
            elif ptype == "enterable":
                raw = self._backend.product_get_enterable()
            elif ptype == "selectable":
                raw = self._backend.product_get_selectable()

            if raw is None:
                raise RuntimeError("Unknown ptype=%s" % ptype)
            ids = raw['ids']
            log.debug("For ptype=%s found ids=%s", ptype, ids)

        kwargs = {}
        if ids:
            kwargs["ids"] = listify(ids)
        if names:
            kwargs["names"] = listify(names)
        if include_fields:
            kwargs["include_fields"] = include_fields
        if exclude_fields:
            kwargs["exclude_fields"] = exclude_fields

        ret = self._backend.product_get(kwargs)
        return ret['products']

    def refresh_products(self, **kwargs):
        """
        Refresh a product's cached info. Basically calls product_get
        with the passed arguments, and tries to intelligently update
        our product cache.

        For example, if we already have cached info for product=foo,
        and you pass in names=["bar", "baz"], the new cache will have
        info for products foo, bar, baz. Individual product fields are
        also updated.
        """
        for product in self.product_get(**kwargs):
            updated = False
            for current in self._cache.products[:]:
                if (current.get("id", -1) != product.get("id", -2) and
                    current.get("name", -1) != product.get("name", -2)):
                    continue

                _nested_update(current, product)
                updated = True
                break
            if not updated:
                self._cache.products.append(product)

    def getproducts(self, force_refresh=False, **kwargs):
        """
        Query all products and return the raw dict info. Takes all the
        same arguments as product_get.

        On first invocation this will contact bugzilla and internally
        cache the results. Subsequent getproducts calls or accesses to
        self.products will return this cached data only.

        :param force_refresh: force refreshing via refresh_products()
        """
        if force_refresh or not self._cache.products:
            self.refresh_products(**kwargs)
        return self._cache.products

    products = property(
        fget=lambda self: self.getproducts(),
        fdel=lambda self: setattr(self, '_products', None),
        doc="Helper for accessing the products cache. If nothing "
            "has been cached yet, this calls getproducts()")


    #######################
    # components querying #
    #######################

    def _lookup_product_in_cache(self, productname):
        prodstr = isinstance(productname, str) and productname or None
        prodint = isinstance(productname, int) and productname or None
        for proddict in self._cache.products:
            if prodstr == proddict.get("name", -1):
                return proddict
            if prodint == proddict.get("id", "nope"):
                return proddict
        return {}

    def getcomponentsdetails(self, product, force_refresh=False):
        """
        Wrapper around Product.get(include_fields=["components"]),
        returning only the "components" data for the requested product,
        slightly reworked to a dict mapping of components.name: components,
        for historical reasons.

        This uses the product cache, but will update it if the product
        isn't found or "components" isn't cached for the product.

        In cases like bugzilla.redhat.com where there are tons of
        components for some products, this API will time out. You
        should use product_get instead.
        """
        proddict = self._lookup_product_in_cache(product)

        if (force_refresh or not proddict or "components" not in proddict):
            self.refresh_products(names=[product],
                                  include_fields=["name", "id", "components"])
            proddict = self._lookup_product_in_cache(product)

        ret = {}
        for compdict in proddict["components"]:
            ret[compdict["name"]] = compdict
        return ret

    def getcomponentdetails(self, product, component, force_refresh=False):
        """
        Helper for accessing a single component's info. This is a wrapper
        around getcomponentsdetails, see that for explanation
        """
        d = self.getcomponentsdetails(product, force_refresh)
        return d[component]

    def getcomponents(self, product, force_refresh=False):
        """
        Return a list of component names for the passed product.

        On first invocation the value is cached, and subsequent calls
        will return the cached data.

        :param force_refresh: Force refreshing the cache, and return
            the new data
        """
        proddict = self._lookup_product_in_cache(product)
        product_id = proddict.get("id", None)

        if (force_refresh or product_id is None or
            "components" not in proddict):
            self.refresh_products(
                names=[product],
                include_fields=["name", "id", "components.name"])
            proddict = self._lookup_product_in_cache(product)
            if "id" not in proddict:
                raise BugzillaError("Product '%s' not found" % product)
            product_id = proddict["id"]

        if product_id not in self._cache.component_names:
            names = []
            for comp in proddict.get("components", []):
                name = comp.get("name")
                if name:
                    names.append(name)
            self._cache.component_names[product_id] = names

        return self._cache.component_names[product_id]


    ############################
    # component adding/editing #
    ############################

    def _component_data_convert(self, data, update=False):
        # Back compat for the old RH interface
        convert_fields = [
            ("initialowner", "default_assignee"),
            ("initialqacontact", "default_qa_contact"),
            ("initialcclist", "default_cc"),
        ]
        for old, new in convert_fields:
            if old in data:
                data[new] = data.pop(old)

        if update:
            names = {"product": data.pop("product"),
                     "component": data.pop("component")}
            updates = {}
            for k in list(data.keys()):
                updates[k] = data.pop(k)

            data["names"] = [names]
            data["updates"] = updates


    def addcomponent(self, data):
        """
        A method to create a component in Bugzilla. Takes a dict, with the
        following elements:

        product: The product to create the component in
        component: The name of the component to create
        description: A one sentence summary of the component
        default_assignee: The bugzilla login (email address) of the initial
                          owner of the component
        default_qa_contact (optional): The bugzilla login of the
                                       initial QA contact
        default_cc: (optional) The initial list of users to be CC'ed on
                               new bugs for the component.
        is_active: (optional) If False, the component is hidden from
                              the component list when filing new bugs.
        """
        data = data.copy()
        self._component_data_convert(data)
        return self._backend.component_create(data)

    def editcomponent(self, data):
        """
        A method to edit a component in Bugzilla. Takes a dict, with
        mandatory elements of product. component, and initialowner.
        All other elements are optional and use the same names as the
        addcomponent() method.
        """
        data = data.copy()
        self._component_data_convert(data, update=True)
        return self._backend.component_update(data)


    ###################
    # getbug* methods #
    ###################

    def _process_include_fields(self, include_fields, exclude_fields,
                                extra_fields):
        """
        Internal helper to process include_fields lists
        """
        def _convert_fields(_in):
            for newname, oldname in self._get_api_aliases():
                if oldname in _in:
                    _in.remove(oldname)
                    if newname not in _in:
                        _in.append(newname)
            return _in

        ret = {}
        if include_fields:
            include_fields = _convert_fields(include_fields)
            if "id" not in include_fields:
                include_fields.append("id")
            ret["include_fields"] = include_fields
        if exclude_fields:
            exclude_fields = _convert_fields(exclude_fields)
            ret["exclude_fields"] = exclude_fields
        if self._supports_getbug_extra_fields():
            if extra_fields:
                ret["extra_fields"] = _convert_fields(extra_fields)
        return ret

    def _get_bug_autorefresh(self):
        """
        This value is passed to Bug.autorefresh for all fetched bugs.
        If True, and an uncached attribute is requested from a Bug,
            the Bug will update its contents and try again.
        """
        return self._bug_autorefresh

    def _set_bug_autorefresh(self, val):
        self._bug_autorefresh = bool(val)
    bug_autorefresh = property(_get_bug_autorefresh, _set_bug_autorefresh)


    def _getbug_extra_fields(self):
        """
        Extra fields that need to be explicitly
        requested from Bug.get in order for the data to be returned.
        """
        rhbz_extra_fields = [
            "comments", "description",
            "external_bugs", "flags", "sub_components",
            "tags",
        ]
        if self._is_redhat_bugzilla:
            return rhbz_extra_fields
        return []

    def _supports_getbug_extra_fields(self):
        """
        Return True if the bugzilla instance supports passing
        extra_fields to getbug

        As of Dec 2012 it seems like only RH bugzilla actually has behavior
        like this, for upstream bz it returns all info for every Bug.get()
        """
        return self._is_redhat_bugzilla


    def _getbugs(self, idlist, permissive,
            include_fields=None, exclude_fields=None, extra_fields=None):
        """
        Return a list of dicts of full bug info for each given bug id.
        bug ids that couldn't be found will return None instead of a dict.
        """
        ids = []
        aliases = []

        def _alias_or_int(_v):
            if str(_v).isdigit():
                return int(_v), None
            return None, str(_v)

        for idstr in idlist:
            idint, alias = _alias_or_int(idstr)
            if alias:
                aliases.append(alias)
            else:
                ids.append(idstr)

        extra_fields = listify(extra_fields or [])
        extra_fields += self._getbug_extra_fields()

        getbugdata = {}
        if permissive:
            getbugdata["permissive"] = 1

        getbugdata.update(self._process_include_fields(
            include_fields, exclude_fields, extra_fields))

        r = self._backend.bug_get(ids, aliases, getbugdata)

        # Do some wrangling to ensure we return bugs in the same order
        # the were passed in, for historical reasons
        ret = []
        for idval in idlist:
            idint, alias = _alias_or_int(idval)
            for bugdict in r["bugs"]:
                if idint and idint != bugdict.get("id", None):
                    continue
                aliaslist = listify(bugdict.get("alias", None) or [])
                if alias and alias not in aliaslist:
                    continue

                ret.append(bugdict)
                break
        return ret

    def _getbug(self, objid, **kwargs):
        """
        Thin wrapper around _getbugs to handle the slight argument tweaks
        for fetching a single bug. The main bit is permissive=False, which
        will tell bugzilla to raise an explicit error if we can't fetch
        that bug.

        This logic is called from Bug() too
        """
        return self._getbugs([objid], permissive=False, **kwargs)[0]

    def getbug(self, objid,
               include_fields=None, exclude_fields=None, extra_fields=None):
        """
        Return a Bug object with the full complement of bug data
        already loaded.
        """
        data = self._getbug(objid,
            include_fields=include_fields, exclude_fields=exclude_fields,
            extra_fields=extra_fields)
        return Bug(self, dict=data, autorefresh=self.bug_autorefresh)

    def getbugs(self, idlist,
                include_fields=None, exclude_fields=None, extra_fields=None,
                permissive=True):
        """
        Return a list of Bug objects with the full complement of bug data
        already loaded. If there's a problem getting the data for a given id,
        the corresponding item in the returned list will be None.
        """
        data = self._getbugs(idlist, include_fields=include_fields,
            exclude_fields=exclude_fields, extra_fields=extra_fields,
            permissive=permissive)
        return [(b and Bug(self, dict=b,
                           autorefresh=self.bug_autorefresh)) or None
                for b in data]

    def get_comments(self, idlist):
        """
        Returns a dictionary of bugs and comments.  The comments key will
        be empty.  See bugzilla docs for details
        """
        return self._backend.bug_comments(idlist, {})


    #################
    # query methods #
    #################

    def build_query(self,
                    product=None,
                    component=None,
                    version=None,
                    long_desc=None,
                    bug_id=None,
                    short_desc=None,
                    cc=None,
                    assigned_to=None,
                    reporter=None,
                    qa_contact=None,
                    status=None,
                    blocked=None,
                    dependson=None,
                    keywords=None,
                    keywords_type=None,
                    url=None,
                    url_type=None,
                    status_whiteboard=None,
                    status_whiteboard_type=None,
                    fixed_in=None,
                    fixed_in_type=None,
                    flag=None,
                    alias=None,
                    qa_whiteboard=None,
                    devel_whiteboard=None,
                    bug_severity=None,
                    priority=None,
                    target_release=None,
                    target_milestone=None,
                    emailtype=None,
                    include_fields=None,
                    quicksearch=None,
                    savedsearch=None,
                    savedsearch_sharer_id=None,
                    sub_component=None,
                    tags=None,
                    exclude_fields=None,
                    extra_fields=None,
                    limit=None):
        """
        Build a query string from passed arguments. Will handle
        query parameter differences between various bugzilla versions.

        Most of the parameters should be self-explanatory. However,
        if you want to perform a complex query, and easy way is to
        create it with the bugzilla web UI, copy the entire URL it
        generates, and pass it to the static method

        Bugzilla.url_to_query

        Then pass the output to Bugzilla.query()

        For details about the specific argument formats, see the bugzilla docs:
        https://bugzilla.readthedocs.io/en/latest/api/core/v1/bug.html#search-bugs
        """
        query = {
            "alias": alias,
            "product": listify(product),
            "component": listify(component),
            "version": version,
            "id": bug_id,
            "short_desc": short_desc,
            "bug_status": status,
            "bug_severity": bug_severity,
            "priority": priority,
            "target_release": target_release,
            "target_milestone": target_milestone,
            "tag": listify(tags),
            "quicksearch": quicksearch,
            "savedsearch": savedsearch,
            "sharer_id": savedsearch_sharer_id,
            "limit": limit,

            # RH extensions... don't add any more. See comment below
            "sub_components": listify(sub_component),
        }

        def add_bool(bzkey, value, bool_id, booltype=None):
            value = listify(value)
            if value is None:
                return bool_id

            query["query_format"] = "advanced"
            for boolval in value:
                def make_bool_str(prefix):
                    # pylint: disable=cell-var-from-loop
                    return "%s%i-0-0" % (prefix, bool_id)

                query[make_bool_str("field")] = bzkey
                query[make_bool_str("value")] = boolval
                query[make_bool_str("type")] = booltype or "substring"

                bool_id += 1
            return bool_id

        # RH extensions that we have to maintain here for back compat,
        # but all future custom fields should be specified via
        # cli --field option, or via extending the query dict() manually.
        # No more supporting custom fields in this API
        bool_id = 0
        bool_id = add_bool("keywords", keywords, bool_id, keywords_type)
        bool_id = add_bool("blocked", blocked, bool_id)
        bool_id = add_bool("dependson", dependson, bool_id)
        bool_id = add_bool("bug_file_loc", url, bool_id, url_type)
        bool_id = add_bool("cf_fixed_in", fixed_in, bool_id, fixed_in_type)
        bool_id = add_bool("flagtypes.name", flag, bool_id)
        bool_id = add_bool("status_whiteboard",
                           status_whiteboard, bool_id, status_whiteboard_type)
        bool_id = add_bool("cf_qa_whiteboard", qa_whiteboard, bool_id)
        bool_id = add_bool("cf_devel_whiteboard", devel_whiteboard, bool_id)

        def add_email(key, value, count):
            if value is None:
                return count
            if not emailtype:
                query[key] = value
                return count

            query["query_format"] = "advanced"
            query['email%i' % count] = value
            query['email%s%i' % (key, count)] = True
            query['emailtype%i' % count] = emailtype
            return count + 1

        email_count = 1
        email_count = add_email("cc", cc, email_count)
        email_count = add_email("assigned_to", assigned_to, email_count)
        email_count = add_email("reporter", reporter, email_count)
        email_count = add_email("qa_contact", qa_contact, email_count)

        if long_desc is not None:
            query["query_format"] = "advanced"
            query["longdesc"] = long_desc
            query["longdesc_type"] = "allwordssubstr"

        # 'include_fields' only available for Bugzilla4+
        # 'extra_fields' is an RHBZ extension
        query.update(self._process_include_fields(
            include_fields, exclude_fields, extra_fields))

        # Strip out None elements in the dict
        for k, v in query.copy().items():
            if v is None:
                del(query[k])

        self.pre_translation(query)
        return query

    def query(self, query):
        """
        Query bugzilla and return a list of matching bugs.
        query must be a dict with fields like those in in querydata['fields'].
        Returns a list of Bug objects.
        Also see the _query() method for details about the underlying
        implementation.
        """
        try:
            r = self._backend.bug_search(query)
            log.debug("bug_search returned:\n%s", str(r))
        except Exception as e:
            # Try to give a hint in the error message if url_to_query
            # isn't supported by this bugzilla instance
            if ("query_format" not in str(e) or
                not BugzillaError.get_bugzilla_error_code(e) or
                self._get_version() >= 5.0):
                raise
            raise BugzillaError("%s\nYour bugzilla instance does not "
                "appear to support API queries derived from bugzilla "
                "web URL queries." % e) from None

        log.debug("Query returned %s bugs", len(r['bugs']))
        return [Bug(self, dict=b,
                autorefresh=self.bug_autorefresh) for b in r['bugs']]

    def pre_translation(self, query):
        """
        In order to keep the API the same, Bugzilla4 needs to process the
        query and the result. This also applies to the refresh() function
        """
        if self._is_redhat_bugzilla:
            _RHBugzillaConverters.pre_translation(query)
            query.update(self._process_include_fields(
                query.get("include_fields", []), None, None))

    def post_translation(self, query, bug):
        """
        In order to keep the API the same, Bugzilla4 needs to process the
        query and the result. This also applies to the refresh() function
        """
        if self._is_redhat_bugzilla:
            _RHBugzillaConverters.post_translation(query, bug)

    def bugs_history_raw(self, bug_ids):
        """
        Experimental. Gets the history of changes for
        particular bugs in the database.
        """
        return self._backend.bug_history(bug_ids, {})


    #######################################
    # Methods for modifying existing bugs #
    #######################################

    # Bug() also has individual methods for many ops, like setassignee()

    def update_bugs(self, ids, updates):
        """
        A thin wrapper around bugzilla Bug.update(). Used to update all
        values of an existing bug report, as well as add comments.

        The dictionary passed to this function should be generated with
        build_update(), otherwise we cannot guarantee back compatibility.
        """
        tmp = updates.copy()
        return self._backend.bug_update(listify(ids), tmp)

    def update_tags(self, idlist, tags_add=None, tags_remove=None):
        """
        Updates the 'tags' field for a bug.
        """
        tags = {}
        if tags_add:
            tags["add"] = listify(tags_add)
        if tags_remove:
            tags["remove"] = listify(tags_remove)

        d = {
            "tags": tags,
        }

        return self._backend.bug_update_tags(listify(idlist), d)

    def update_flags(self, idlist, flags):
        """
        A thin back compat wrapper around build_update(flags=X)
        """
        return self.update_bugs(idlist, self.build_update(flags=flags))


    def build_update(self,
                     alias=None,
                     assigned_to=None,
                     blocks_add=None,
                     blocks_remove=None,
                     blocks_set=None,
                     depends_on_add=None,
                     depends_on_remove=None,
                     depends_on_set=None,
                     cc_add=None,
                     cc_remove=None,
                     is_cc_accessible=None,
                     comment=None,
                     comment_private=None,
                     component=None,
                     deadline=None,
                     dupe_of=None,
                     estimated_time=None,
                     groups_add=None,
                     groups_remove=None,
                     keywords_add=None,
                     keywords_remove=None,
                     keywords_set=None,
                     op_sys=None,
                     platform=None,
                     priority=None,
                     product=None,
                     qa_contact=None,
                     is_creator_accessible=None,
                     remaining_time=None,
                     reset_assigned_to=None,
                     reset_qa_contact=None,
                     resolution=None,
                     see_also_add=None,
                     see_also_remove=None,
                     severity=None,
                     status=None,
                     summary=None,
                     target_milestone=None,
                     target_release=None,
                     url=None,
                     version=None,
                     whiteboard=None,
                     work_time=None,
                     fixed_in=None,
                     qa_whiteboard=None,
                     devel_whiteboard=None,
                     internal_whiteboard=None,
                     sub_component=None,
                     flags=None,
                     comment_tags=None,
                     minor_update=None):
        """
        Returns a python dict() with properly formatted parameters to
        pass to update_bugs(). See bugzilla documentation for the format
        of the individual fields:

        https://bugzilla.readthedocs.io/en/latest/api/core/v1/bug.html#create-bug
        """
        ret = {}
        rhbzret = {}

        # These are only supported for rhbugzilla
        #
        # This should not be extended any more.
        # If people want to handle custom fields, manually extend the
        # returned dictionary.
        rhbzargs = {
            "fixed_in": fixed_in,
            "devel_whiteboard": devel_whiteboard,
            "qa_whiteboard": qa_whiteboard,
            "internal_whiteboard": internal_whiteboard,
            "sub_component": sub_component,
        }
        if self._is_redhat_bugzilla:
            rhbzret = _RHBugzillaConverters.convert_build_update(
                component=component, **rhbzargs)
        else:
            for key, val in rhbzargs.items():
                if val is not None:
                    raise ValueError("bugzilla instance does not support "
                                     "updating '%s'" % key)

        def s(key, val, convert=None):
            if val is None:
                return
            if convert:
                val = convert(val)
            ret[key] = val

        def add_dict(key, add, remove, _set=None, convert=None):
            if add is remove is _set is None:
                return

            def c(val):
                val = listify(val)
                if convert:
                    val = [convert(v) for v in val]
                return val

            newdict = {}
            if add is not None:
                newdict["add"] = c(add)
            if remove is not None:
                newdict["remove"] = c(remove)
            if _set is not None:
                newdict["set"] = c(_set)
            ret[key] = newdict


        s("alias", alias)
        s("assigned_to", assigned_to)
        s("is_cc_accessible", is_cc_accessible, bool)
        s("component", component)
        s("deadline", deadline)
        s("dupe_of", dupe_of, int)
        s("estimated_time", estimated_time, int)
        s("op_sys", op_sys)
        s("platform", platform)
        s("priority", priority)
        s("product", product)
        s("qa_contact", qa_contact)
        s("is_creator_accessible", is_creator_accessible, bool)
        s("remaining_time", remaining_time, float)
        s("reset_assigned_to", reset_assigned_to, bool)
        s("reset_qa_contact", reset_qa_contact, bool)
        s("resolution", resolution)
        s("severity", severity)
        s("status", status)
        s("summary", summary)
        s("target_milestone", target_milestone)
        s("target_release", target_release)
        s("url", url)
        s("version", version)
        s("whiteboard", whiteboard)
        s("work_time", work_time, float)
        s("flags", flags)
        s("comment_tags", comment_tags, listify)
        s("minor_update", minor_update, bool)

        add_dict("blocks", blocks_add, blocks_remove, blocks_set,
                 convert=int)
        add_dict("depends_on", depends_on_add, depends_on_remove,
                 depends_on_set, convert=int)
        add_dict("cc", cc_add, cc_remove)
        add_dict("groups", groups_add, groups_remove)
        add_dict("keywords", keywords_add, keywords_remove, keywords_set)
        add_dict("see_also", see_also_add, see_also_remove)

        if comment is not None:
            ret["comment"] = {"comment": comment}
            if comment_private:
                ret["comment"]["is_private"] = comment_private

        ret.update(rhbzret)
        return ret


    ########################################
    # Methods for working with attachments #
    ########################################

    def attachfile(self, idlist, attachfile, description, **kwargs):
        """
        Attach a file to the given bug IDs. Returns the ID of the attachment
        or raises XMLRPC Fault if something goes wrong.

        attachfile may be a filename (which will be opened) or a file-like
        object, which must provide a 'read' method. If it's not one of these,
        this method will raise a TypeError.
        description is the short description of this attachment.

        Optional keyword args are as follows:
            file_name:  this will be used as the filename for the attachment.
                       REQUIRED if attachfile is a file-like object with no
                       'name' attribute, otherwise the filename or .name
                       attribute will be used.
            comment:   An optional comment about this attachment.
            is_private: Set to True if the attachment should be marked private.
            is_patch:   Set to True if the attachment is a patch.
            content_type: The mime-type of the attached file. Defaults to
                          application/octet-stream if not set. NOTE that text
                          files will *not* be viewable in bugzilla unless you
                          remember to set this to text/plain. So remember that!

        Returns the list of attachment ids that were added. If only one
        attachment was added, we return the single int ID for back compat
        """
        if isinstance(attachfile, str):
            f = open(attachfile, "rb")
        elif hasattr(attachfile, 'read'):
            f = attachfile
        else:
            raise TypeError("attachfile must be filename or file-like object")

        # Back compat
        if "contenttype" in kwargs:
            kwargs["content_type"] = kwargs.pop("contenttype")
        if "ispatch" in kwargs:
            kwargs["is_patch"] = kwargs.pop("ispatch")
        if "isprivate" in kwargs:
            kwargs["is_private"] = kwargs.pop("isprivate")
        if "filename" in kwargs:
            kwargs["file_name"] = kwargs.pop("filename")

        kwargs['summary'] = description

        data = f.read()
        if not isinstance(data, bytes):  # pragma: no cover
            data = data.encode(locale.getpreferredencoding())

        if 'file_name' not in kwargs and hasattr(f, "name"):
            kwargs['file_name'] = os.path.basename(f.name)
        if 'content_type' not in kwargs:
            ctype = None
            if kwargs['file_name']:
                ctype = mimetypes.guess_type(
                    kwargs['file_name'], strict=False)[0]
            kwargs['content_type'] = ctype or 'application/octet-stream'

        ret = self._backend.bug_attachment_create(
            listify(idlist), data, kwargs)

        if "attachments" in ret:
            # Up to BZ 4.2
            ret = [int(k) for k in ret["attachments"].keys()]
        elif "ids" in ret:
            # BZ 4.4+
            ret = ret["ids"]

        if isinstance(ret, list) and len(ret) == 1:
            ret = ret[0]
        return ret

    def openattachment_data(self, attachment_dict):
        """
        Helper for turning passed API attachment dictionary into a
        filelike object
        """
        ret = BytesIO()
        data = attachment_dict["data"]

        if hasattr(data, "data"):
            # This is for xmlrpc Binary
            content = data.data  # pragma: no cover
        else:
            import base64
            content = base64.b64decode(data)

        ret.write(content)
        ret.name = attachment_dict["file_name"]
        ret.seek(0)
        return ret

    def openattachment(self, attachid):
        """
        Get the contents of the attachment with the given attachment ID.
        Returns a file-like object.
        """
        attachments = self.get_attachments(None, attachid)
        data = attachments["attachments"][str(attachid)]
        return self.openattachment_data(data)

    def updateattachmentflags(self, bugid, attachid, flagname, **kwargs):
        """
        Updates a flag for the given attachment ID.
        Optional keyword args are:
            status:    new status for the flag ('-', '+', '?', 'X')
            requestee: new requestee for the flag
        """
        # Bug ID was used for the original custom redhat API, no longer
        # needed though
        ignore = bugid

        flags = {"name": flagname}
        flags.update(kwargs)
        attachment_ids = [int(attachid)]
        update = {'flags': [flags]}

        return self._backend.bug_attachment_update(attachment_ids, update)

    def get_attachments(self, ids, attachment_ids,
                        include_fields=None, exclude_fields=None):
        """
        Wrapper for Bug.attachments. One of ids or attachment_ids is required

        :param ids: Get attachments for this bug ID
        :param attachment_ids: Specific attachment ID to get

        https://bugzilla.readthedocs.io/en/latest/api/core/v1/attachment.html#get-attachment
        """
        params = {}
        if include_fields:
            params["include_fields"] = listify(include_fields)
        if exclude_fields:
            params["exclude_fields"] = listify(exclude_fields)

        if attachment_ids:
            return self._backend.bug_attachment_get(attachment_ids, params)
        return self._backend.bug_attachment_get_all(ids, params)


    #####################
    # createbug methods #
    #####################

    createbug_required = ('product', 'component', 'summary', 'version',
                          'description')

    def build_createbug(self,
        product=None,
        component=None,
        version=None,
        summary=None,
        description=None,
        comment_private=None,
        blocks=None,
        cc=None,
        assigned_to=None,
        keywords=None,
        depends_on=None,
        groups=None,
        op_sys=None,
        platform=None,
        priority=None,
        qa_contact=None,
        resolution=None,
        severity=None,
        status=None,
        target_milestone=None,
        target_release=None,
        url=None,
        sub_component=None,
        alias=None,
        comment_tags=None):
        """
        Returns a python dict() with properly formatted parameters to
        pass to createbug(). See bugzilla documentation for the format
        of the individual fields:

        https://bugzilla.readthedocs.io/en/latest/api/core/v1/bug.html#update-bug
        """

        localdict = {}
        if blocks:
            localdict["blocks"] = listify(blocks)
        if cc:
            localdict["cc"] = listify(cc)
        if depends_on:
            localdict["depends_on"] = listify(depends_on)
        if groups:
            localdict["groups"] = listify(groups)
        if keywords:
            localdict["keywords"] = listify(keywords)
        if description:
            localdict["description"] = description
            if comment_private:
                localdict["comment_is_private"] = True

        # Most of the machinery and formatting here is the same as
        # build_update, so reuse that as much as possible
        ret = self.build_update(product=product, component=component,
                version=version, summary=summary, op_sys=op_sys,
                platform=platform, priority=priority, qa_contact=qa_contact,
                resolution=resolution, severity=severity, status=status,
                target_milestone=target_milestone,
                target_release=target_release, url=url,
                assigned_to=assigned_to, sub_component=sub_component,
                alias=alias, comment_tags=comment_tags)

        ret.update(localdict)
        return ret

    def _validate_createbug(self, *args, **kwargs):
        # Previous API required users specifying keyword args that mapped
        # to the XMLRPC arg names. Maintain that bad compat, but also allow
        # receiving a single dictionary like query() does
        if kwargs and args:  # pragma: no cover
            raise BugzillaError("createbug: cannot specify positional "
                                "args=%s with kwargs=%s, must be one or the "
                                "other." % (args, kwargs))
        if args:
            if len(args) > 1 or not isinstance(args[0], dict):
                raise BugzillaError(  # pragma: no cover
                    "createbug: positional arguments only "
                    "accept a single dictionary.")
            data = args[0]
        else:
            data = kwargs

        # If we're getting a call that uses an old fieldname, convert it to the
        # new fieldname instead.
        for newname, oldname in self._get_api_aliases():
            if (newname in self.createbug_required and
                newname not in data and
                oldname in data):
                data[newname] = data.pop(oldname)

        # Back compat handling for check_args
        if "check_args" in data:
            del(data["check_args"])

        return data

    def createbug(self, *args, **kwargs):
        """
        Create a bug with the given info. Returns a new Bug object.
        Check bugzilla API documentation for valid values, at least
        product, component, summary, version, and description need to
        be passed.
        """
        data = self._validate_createbug(*args, **kwargs)
        rawbug = self._backend.bug_create(data)
        return Bug(self, bug_id=rawbug["id"],
                   autorefresh=self.bug_autorefresh)


    ##############################
    # Methods for handling Users #
    ##############################

    def getuser(self, username):
        """
        Return a bugzilla User for the given username

        :arg username: The username used in bugzilla.
        :raises XMLRPC Fault: Code 51 if the username does not exist
        :returns: User record for the username
        """
        ret = self.getusers(username)
        return ret and ret[0]

    def getusers(self, userlist):
        """
        Return a list of Users from .

        :userlist: List of usernames to lookup
        :returns: List of User records
        """
        userlist = listify(userlist)
        rawusers = self._backend.user_get({"names": userlist})
        userobjs = [User(self, **rawuser) for rawuser in
                    rawusers.get('users', [])]

        # Return users in same order they were passed in
        ret = []
        for u in userlist:
            for uobj in userobjs[:]:
                if uobj.email == u:
                    userobjs.remove(uobj)
                    ret.append(uobj)
                    break
        ret += userobjs
        return ret


    def searchusers(self, pattern):
        """
        Return a bugzilla User for the given list of patterns

        :arg pattern: List of patterns to match against.
        :returns: List of User records
        """
        rawusers = self._backend.user_get({"match": listify(pattern)})
        return [User(self, **rawuser) for rawuser in
                rawusers.get('users', [])]

    def createuser(self, email, name='', password=''):
        """
        Return a bugzilla User for the given username

        :arg email: The email address to use in bugzilla
        :kwarg name: Real name to associate with the account
        :kwarg password: Password to set for the bugzilla account
        :raises XMLRPC Fault: Code 501 if the username already exists
            Code 500 if the email address isn't valid
            Code 502 if the password is too short
            Code 503 if the password is too long
        :return: User record for the username
        """
        args = {"email": email}
        if name:
            args["name"] = name
        if password:
            args["password"] = password
        self._backend.user_create(args)
        return self.getuser(email)

    def updateperms(self, user, action, groups):
        """
        A method to update the permissions (group membership) of a bugzilla
        user.

        :arg user: The e-mail address of the user to be acted upon. Can
            also be a list of emails.
        :arg action: add, remove, or set
        :arg groups: list of groups to be added to (i.e. ['fedora_contrib'])
        """
        groups = listify(groups)
        if action == "rem":
            action = "remove"
        if action not in ["add", "remove", "set"]:
            raise BugzillaError("Unknown user permission action '%s'" % action)

        update = {
            "names": listify(user),
            "groups": {
                action: groups,
            }
        }

        return self._backend.user_update(update)


    ###############################
    # Methods for handling Groups #
    ###############################

    def _getgroups(self, names, membership=False):
        """
        Return a list of groups that match criteria.

        :kwarg ids: list of group ids to return data on
        :kwarg membership: boolean specifying wether to query the members
            of the group or not.
        :raises XMLRPC Fault: Code 51: if a Bad Login Name was sent to the
                names array.
            Code 304: if the user was not authorized to see user they
                requested.
            Code 505: user is logged out and can't use the match or ids
                parameter.
            Code 805: logged in user do not have enough priviledges to view
                groups.
        """
        params = {"membership": membership}
        params['names'] = listify(names)
        return self._backend.group_get(params)

    def getgroup(self, name, membership=False):
        """
        Return a bugzilla Group for the given name

        :arg name: The group name used in bugzilla.
        :raises XMLRPC Fault: Code 51 if the name does not exist
        :raises XMLRPC Fault: Code 805 if the user does not have enough
            permissions to view groups
        :returns: Group record for the name
        """
        ret = self.getgroups(name, membership=membership)
        return ret and ret[0]

    def getgroups(self, grouplist, membership=False):
        """
        Return a list of Groups from .

        :userlist: List of group names to lookup
        :returns: List of Group records
        """
        grouplist = listify(grouplist)
        groupobjs = [
            Group(self, **rawgroup)
            for rawgroup in self._getgroups(
                names=grouplist, membership=membership).get('groups', [])
        ]

        # Return in same order they were passed in
        ret = []
        for g in grouplist:
            for gobj in groupobjs[:]:
                if gobj.name == g:
                    groupobjs.remove(gobj)
                    ret.append(gobj)
                    break
        ret += groupobjs
        return ret


    #############################
    # ExternalBugs API wrappers #
    #############################

    def add_external_tracker(self, bug_ids, ext_bz_bug_id, ext_type_id=None,
                             ext_type_description=None, ext_type_url=None,
                             ext_status=None, ext_description=None,
                             ext_priority=None):
        """
        Wrapper method to allow adding of external tracking bugs using the
        ExternalBugs::WebService::add_external_bug method.

        This is documented at
        https://bugzilla.redhat.com/docs/en/html/integrating/api/Bugzilla/Extension/ExternalBugs/WebService.html#add-external-bug

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
            'bug_ids': listify(bug_ids),
            'external_bugs': [param_dict],
        }
        return self._backend.externalbugs_add(params)

    def update_external_tracker(self, ids=None, ext_type_id=None,
                                ext_type_description=None, ext_type_url=None,
                                ext_bz_bug_id=None, bug_ids=None,
                                ext_status=None, ext_description=None,
                                ext_priority=None):
        """
        Wrapper method to allow adding of external tracking bugs using the
        ExternalBugs::WebService::update_external_bug method.

        This is documented at
        https://bugzilla.redhat.com/docs/en/html/integrating/api/Bugzilla/Extension/ExternalBugs/WebService.html#update-external-bug

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
            params['ids'] = listify(ids)
        if ext_type_id is not None:
            params['ext_type_id'] = ext_type_id
        if ext_type_description is not None:
            params['ext_type_description'] = ext_type_description
        if ext_type_url is not None:
            params['ext_type_url'] = ext_type_url
        if ext_bz_bug_id is not None:
            params['ext_bz_bug_id'] = listify(ext_bz_bug_id)
        if bug_ids is not None:
            params['bug_ids'] = listify(bug_ids)
        if ext_status is not None:
            params['ext_status'] = ext_status
        if ext_description is not None:
            params['ext_description'] = ext_description
        if ext_priority is not None:
            params['ext_priority'] = ext_priority
        return self._backend.externalbugs_update(params)

    def remove_external_tracker(self, ids=None, ext_type_id=None,
                                ext_type_description=None, ext_type_url=None,
                                ext_bz_bug_id=None, bug_ids=None):
        """
        Wrapper method to allow removal of external tracking bugs using the
        ExternalBugs::WebService::remove_external_bug method.

        This is documented at
        https://bugzilla.redhat.com/docs/en/html/integrating/api/Bugzilla/Extension/ExternalBugs/WebService.html#remove-external-bug

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
            params['ids'] = listify(ids)
        if ext_type_id is not None:
            params['ext_type_id'] = ext_type_id
        if ext_type_description is not None:
            params['ext_type_description'] = ext_type_description
        if ext_type_url is not None:
            params['ext_type_url'] = ext_type_url
        if ext_bz_bug_id is not None:
            params['ext_bz_bug_id'] = listify(ext_bz_bug_id)
        if bug_ids is not None:
            params['bug_ids'] = listify(bug_ids)
        return self._backend.externalbugs_remove(params)
