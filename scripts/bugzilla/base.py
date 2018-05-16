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

import collections
import getpass
import locale
from logging import getLogger
import os
import sys

from io import BytesIO

# pylint: disable=import-error
if sys.version_info[0] >= 3:
    # pylint: disable=no-name-in-module
    from configparser import SafeConfigParser
    from http.cookiejar import LoadError, MozillaCookieJar
    from urllib.parse import urlparse, parse_qsl
    from xmlrpc.client import Binary, Fault
else:
    from ConfigParser import SafeConfigParser
    from cookielib import LoadError, MozillaCookieJar
    from urlparse import urlparse, parse_qsl
    from xmlrpclib import Binary, Fault
# pylint: enable=import-error


from .apiversion import __version__
from .bug import Bug, User
from .transport import BugzillaError, _BugzillaServerProxy, _RequestsTransport


log = getLogger(__name__)

mimemagic = None


def _detect_filetype(fname):
    global mimemagic

    if mimemagic is None:
        try:
            # pylint: disable=import-error
            import magic
            mimemagic = magic.open(getattr(magic, "MAGIC_MIME_TYPE", 16))
            mimemagic.load()
        except ImportError as e:
            log.debug("Could not load python-magic: %s", e)
            mimemagic = None
    if not mimemagic:
        return None

    if not os.path.isabs(fname):
        return None

    try:
        return mimemagic.file(fname)
    except Exception as e:
        log.debug("Could not detect content_type: %s", e)
    return None


def _nested_update(d, u):
    # Helper for nested dict update()
    # https://stackoverflow.com/questions/3232943/update-value-of-a-nested-dictionary-of-varying-depth
    for k, v in list(u.items()):
        if isinstance(v, collections.Mapping):
            d[k] = _nested_update(d.get(k, {}), v)
        else:
            d[k] = v
    return d


def _default_auth_location(filename):
    """
    Determine auth location for filename, like 'bugzillacookies'. If
    old style ~/.bugzillacookies exists, we use that, otherwise we
    use ~/.cache/python-bugzilla/bugzillacookies. Same for bugzillatoken
    """
    homepath = os.path.expanduser("~/.%s" % filename)
    xdgpath = os.path.expanduser("~/.cache/python-bugzilla/%s" % filename)
    if os.path.exists(xdgpath):
        return xdgpath
    if os.path.exists(homepath):
        return homepath

    if not os.path.exists(os.path.dirname(xdgpath)):
        os.makedirs(os.path.dirname(xdgpath), 0o700)
    return xdgpath


def _build_cookiejar(cookiefile):
    cj = MozillaCookieJar(cookiefile)
    if cookiefile is None:
        return cj
    if not os.path.exists(cookiefile):
        # Make sure a new file has correct permissions
        open(cookiefile, 'a').close()
        os.chmod(cookiefile, 0o600)
        cj.save()
        return cj

    try:
        cj.load()
        return cj
    except LoadError:
        raise BugzillaError("cookiefile=%s not in Mozilla format" %
                            cookiefile)


_default_configpaths = [
    '/etc/bugzillarc',
    '~/.bugzillarc',
    '~/.config/python-bugzilla/bugzillarc',
]


def _open_bugzillarc(configpaths=-1):
    if configpaths == -1:
        configpaths = _default_configpaths[:]

    # pylint: disable=protected-access
    configpaths = [os.path.expanduser(p) for p in
                   Bugzilla._listify(configpaths)]
    # pylint: enable=protected-access
    cfg = SafeConfigParser()
    read_files = cfg.read(configpaths)
    if not read_files:
        return

    log.info("Found bugzillarc files: %s", read_files)
    return cfg


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


class Bugzilla(object):
    """
    The main API object. Connects to a bugzilla instance over XMLRPC, and
    provides wrapper functions to simplify dealing with API calls.

    The most common invocation here will just be with just a URL:

        bzapi = Bugzilla("http://bugzilla.example.com")

    If you have previously logged into that URL, and have cached login
    cookies/tokens, you will automatically be logged in. Otherwise to
    log in, you can either pass auth options to __init__, or call a login
    helper like interactive_login().

    If you are not logged in, you won be able to access restricted data like
    user email, or perform write actions like bug create/update. But simple
    querys will work correctly.

    If you are unsure if you are logged in, you can check the .logged_in
    property.

    Another way to specify auth credentials is via a 'bugzillarc' file.
    See readconfig() documentation for details.
    """

    # bugzilla version that the class is targeting. filled in by
    # subclasses
    bz_ver_major = 0
    bz_ver_minor = 0

    @staticmethod
    def url_to_query(url):
        '''
        Given a big huge bugzilla query URL, returns a query dict that can
        be passed along to the Bugzilla.query() method.
        '''
        q = {}

        # pylint: disable=unpacking-non-sequence
        (ignore, ignore, path,
         ignore, query, ignore) = urlparse(url)

        base = os.path.basename(path)
        if base not in ('buglist.cgi', 'query.cgi'):
            return {}

        for (k, v) in parse_qsl(query):
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
    def fix_url(url):
        """
        Turn passed url into a bugzilla XMLRPC web url
        """
        if '://' not in url:
            log.debug('No scheme given for url, assuming https')
            url = 'https://' + url
        if url.count('/') < 3:
            log.debug('No path given for url, assuming /xmlrpc.cgi')
            url = url + '/xmlrpc.cgi'
        return url

    @staticmethod
    def _listify(val):
        if val is None:
            return val
        if isinstance(val, list):
            return val
        return [val]


    def __init__(self, url=-1, user=None, password=None, cookiefile=-1,
                 sslverify=True, tokenfile=-1, use_creds=True, api_key=None,
                 cert=None, authtype=None):
        """
        :param url: The bugzilla instance URL, which we will connect
            to immediately. Most users will want to specify this at
            __init__ time, but you can defer connecting by passing
            url=None and calling connect(URL) manually
        :param user: optional username to connect with
        :param password: optional password for the connecting user
        :param cert: optional certificate file for client side certificate
            authentication
        :param cookiefile: Location to cache the login session cookies so you
            don't have to keep specifying username/password. Bugzilla 5+ will
            use tokens instead of cookies.
            If -1, use the default path. If None, don't use or save
            any cookiefile.
        :param sslverify: Set this to False to skip SSL hostname and CA
            validation checks, like out of date certificate
        :param tokenfile: Location to cache the API login token so youi
            don't have to keep specifying username/password.
            If -1, use the default path. If None, don't use
            or save any tokenfile.
        :param use_creds: If False, this disables cookiefile, tokenfile,
            and any bugzillarc reading. This overwrites any tokenfile
            or cookiefile settings
        :param sslverify: Maps to 'requests' sslverify parameter. Set to
            False to disable SSL verification, but it can also be a path
            to file or directory for custom certs.
        :param api_key: A bugzilla
        :param authtype: Authentication type: empty or 'basic'
        """
        if url == -1:
            raise TypeError("Specify a valid bugzilla url, or pass url=None")

        # Settings the user might want to tweak
        self.user = user or ''
        self.password = password or ''
        self.api_key = api_key
        self.cert = cert or ''
        self.url = ''
        self.authtype = authtype or ''

        self._proxy = None
        self._transport = None
        self._cookiejar = None
        self._sslverify = sslverify
        self._cache = _BugzillaAPICache()
        self._bug_autorefresh = False

        self._field_aliases = []
        self._init_field_aliases()

        self.configpath = _default_configpaths[:]
        if not use_creds:
            cookiefile = None
            tokenfile = None
            self.configpath = []

        if cookiefile == -1:
            cookiefile = _default_auth_location("bugzillacookies")
        if tokenfile == -1:
            tokenfile = _default_auth_location("bugzillatoken")
        log.debug("Using tokenfile=%s", tokenfile)
        self.cookiefile = cookiefile
        self.tokenfile = tokenfile

        if url:
            self.connect(url)
            self._init_class_from_url()
        self._init_class_state()

    def _init_class_from_url(self):
        """
        Detect if we should use RHBugzilla class, and if so, set it
        """
        from bugzilla import RHBugzilla
        if isinstance(self, RHBugzilla):
            return

        c = None
        if "bugzilla.redhat.com" in self.url:
            log.info("Using RHBugzilla for URL containing bugzilla.redhat.com")
            c = RHBugzilla
        else:
            try:
                extensions = self._proxy.Bugzilla.extensions()
                if "RedHat" in extensions.get('extensions', {}):
                    log.info("Found RedHat bugzilla extension, "
                        "using RHBugzilla")
                    c = RHBugzilla
            except Fault:
                log.debug("Failed to fetch bugzilla extensions", exc_info=True)

        if not c:
            return

        self.__class__ = c

    def _init_class_state(self):
        """
        Hook for subclasses to do any __init__ time setup
        """
        pass

    def _init_field_aliases(self):
        # List of field aliases. Maps old style RHBZ parameter
        # names to actual upstream values. Used for createbug() and
        # query include_fields at least.
        self._add_field_alias('summary', 'short_desc')
        self._add_field_alias('description', 'comment')
        self._add_field_alias('platform', 'rep_platform')
        self._add_field_alias('severity', 'bug_severity')
        self._add_field_alias('status', 'bug_status')
        self._add_field_alias('id', 'bug_id')
        self._add_field_alias('blocks', 'blockedby')
        self._add_field_alias('blocks', 'blocked')
        self._add_field_alias('depends_on', 'dependson')
        self._add_field_alias('creator', 'reporter')
        self._add_field_alias('url', 'bug_file_loc')
        self._add_field_alias('dupe_of', 'dupe_id')
        self._add_field_alias('dupe_of', 'dup_id')
        self._add_field_alias('comments', 'longdescs')
        self._add_field_alias('creation_time', 'opendate')
        self._add_field_alias('creation_time', 'creation_ts')
        self._add_field_alias('whiteboard', 'status_whiteboard')
        self._add_field_alias('last_change_time', 'delta_ts')

    def _get_user_agent(self):
        return 'python-bugzilla/%s' % __version__
    user_agent = property(_get_user_agent)


    ###################
    # Private helpers #
    ###################

    def _check_version(self, major, minor):
        """
        Check if the detected bugzilla version is >= passed major/minor pair.
        """
        if major < self.bz_ver_major:
            return True
        if (major == self.bz_ver_major and minor <= self.bz_ver_minor):
            return True
        return False

    def _add_field_alias(self, *args, **kwargs):
        self._field_aliases.append(_FieldAlias(*args, **kwargs))

    def _get_bug_aliases(self):
        return [(f.newname, f.oldname)
                for f in self._field_aliases if f.is_bug]

    def _get_api_aliases(self):
        return [(f.newname, f.oldname)
                for f in self._field_aliases if f.is_api]


    ###################
    # Cookie handling #
    ###################

    def _getcookiefile(self):
        '''cookiefile is the file that bugzilla session cookies are loaded
        and saved from.
        '''
        return self._cookiejar.filename

    def _delcookiefile(self):
        self._cookiejar = None

    def _setcookiefile(self, cookiefile):
        if (self._cookiejar and cookiefile == self._cookiejar.filename):
            return

        if self._proxy is not None:
            raise RuntimeError("Can't set cookies with an open connection, "
                               "disconnect() first.")

        log.debug("Using cookiefile=%s", cookiefile)
        self._cookiejar = _build_cookiejar(cookiefile)

    cookiefile = property(_getcookiefile, _setcookiefile, _delcookiefile)


    #############################
    # Login/connection handling #
    #############################

    def readconfig(self, configpath=None):
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
        """
        cfg = _open_bugzillarc(configpath or self.configpath)
        if not cfg:
            return

        section = ""
        log.debug("bugzillarc: Searching for config section matching %s",
            self.url)
        for s in sorted(cfg.sections()):
            # Substring match - prefer the longest match found
            if s in self.url:
                log.debug("bugzillarc: Found matching section: %s", s)
                section = s

        if not section:
            log.debug("bugzillarc: No section found")
            return

        for key, val in cfg.items(section):
            if key == "api_key":
                log.debug("bugzillarc: setting api_key")
                self.api_key = val
            elif key == "user":
                log.debug("bugzillarc: setting user=%s", val)
                self.user = val
            elif key == "password":
                log.debug("bugzillarc: setting password")
                self.password = val
            elif key == "cert":
                log.debug("bugzillarc: setting cert")
                self.cert = val
            elif key == "authtype":
                log.debug("bugzillarc: setting authtype=%s", val)
                self.authtype = val
            else:
                log.debug("bugzillarc: unknown key=%s", key)

    def _set_bz_version(self, version):
        try:
            self.bz_ver_major, self.bz_ver_minor = [
                int(i) for i in version.split(".")[0:2]]
        except Exception:
            log.debug("version doesn't match expected format X.Y.Z, "
                    "assuming 5.0", exc_info=True)
            self.bz_ver_major = 5
            self.bz_ver_minor = 0

    def connect(self, url=None):
        '''
        Connect to the bugzilla instance with the given url. This is
        called by __init__ if a URL is passed. Or it can be called manually
        at any time with a passed URL.

        This will also read any available config files (see readconfig()),
        which may set 'user' and 'password', and others.

        If 'user' and 'password' are both set, we'll run login(). Otherwise
        you'll have to login() yourself before some methods will work.
        '''
        if self._transport:
            self.disconnect()

        if url is None and self.url:
            url = self.url
        url = self.fix_url(url)

        self.url = url
        # we've changed URLs - reload config
        self.readconfig()

        self._transport = _RequestsTransport(
            url, self._cookiejar, sslverify=self._sslverify, cert=self.cert)
        if self.authtype == 'basic' and self.user and self.password:
            self._transport.session.auth = (self.user, self.password)
        self._transport.user_agent = self.user_agent
        self._proxy = _BugzillaServerProxy(url, self.tokenfile,
            self._transport)

        if (self.authtype == '' and self.user and self.password):
            log.info("user and password present - doing login()")
            self.login()

        if self.api_key:
            log.debug("using API key")
            self._proxy.use_api_key(self.api_key)

        version = self._proxy.Bugzilla.version()["version"]
        log.debug("Bugzilla version string: %s", version)
        self._set_bz_version(version)

    def disconnect(self):
        '''
        Disconnect from the given bugzilla instance.
        '''
        self._proxy = None
        self._transport = None
        self._cache = _BugzillaAPICache()


    def _login(self, user, password):
        '''Backend login method for Bugzilla3'''
        return self._proxy.User.login({'login': user, 'password': password})

    def _logout(self):
        '''Backend login method for Bugzilla3'''
        return self._proxy.User.logout()

    def login(self, user=None, password=None):
        '''Attempt to log in using the given username and password. Subsequent
        method calls will use this username and password. Returns False if
        login fails, otherwise returns some kind of login info - typically
        either a numeric userid, or a dict of user info.

        If user is not set, the value of Bugzilla.user will be used. If *that*
        is not set, ValueError will be raised. If login fails, BugzillaError
        will be raised.

        This method will be called implicitly at the end of connect() if user
        and password are both set. So under most circumstances you won't need
        to call this yourself.
        '''
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

        try:
            ret = self._login(self.user, self.password)
            self.password = ''
            log.info("login successful for user=%s", self.user)
            return ret
        except Fault as e:
            raise BugzillaError("Login failed: %s" % str(e.faultString))

    def interactive_login(self, user=None, password=None, force=False):
        """
        Helper method to handle login for this bugzilla instance.

        :param user: bugzilla username. If not specified, prompt for it.
        :param password: bugzilla password. If not specified, prompt for it.
        :param force: Unused
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
        self.login(user, password)
        log.info('Authorization cookie received.')

    def logout(self):
        '''Log out of bugzilla. Drops server connection and user info, and
        destroys authentication cookies.'''
        self._logout()
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
            self._proxy.User.get({'ids': []})
            return True
        except Fault as e:
            if e.faultCode == 505 or e.faultCode == 32000:
                return False
            raise e


    ######################
    # Bugfields querying #
    ######################

    def _getbugfields(self):
        '''
        Get the list of valid fields for Bug objects
        '''
        r = self._proxy.Bug.fields({'include_fields': ['name']})
        return [f['name'] for f in r['fields']]

    def getbugfields(self, force_refresh=False):
        '''
        Calls getBugFields, which returns a list of fields in each bug
        for this bugzilla instance. This can be used to set the list of attrs
        on the Bug object.
        '''
        if force_refresh or not self._cache.bugfields:
            log.debug("Refreshing bugfields")
            self._cache.bugfields = self._getbugfields()
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
                raw = self._proxy.Product.get_accessible_products()
            elif ptype == "selectable":
                raw = self._proxy.Product.get_selectable_products()
            elif ptype == "enterable":
                raw = self._proxy.Product.get_enterable_products()

            if raw is None:
                raise RuntimeError("Unknown ptype=%s" % ptype)
            ids = raw['ids']
            log.debug("For ptype=%s found ids=%s", ptype, ids)

        kwargs = {}
        if ids:
            kwargs["ids"] = self._listify(ids)
        if names:
            kwargs["names"] = self._listify(names)
        if include_fields:
            kwargs["include_fields"] = include_fields
        if exclude_fields:
            kwargs["exclude_fields"] = exclude_fields

        log.debug("Calling Product.get with: %s", kwargs)
        ret = self._proxy.Product.get(kwargs)
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

        This can be implemented with Product.get, but behind the
        scenes it uses Bug.legal_values. Reason being that on bugzilla
        instances with tons of components, like bugzilla.redhat.com
        Product=Fedora for example, there's a 10x speed difference
        even with properly limited Product.get calls.

        On first invocation the value is cached, and subsequent calls
        will return the cached data.

        :param force_refresh: Force refreshing the cache, and return
            the new data
        """
        proddict = self._lookup_product_in_cache(product)
        product_id = proddict.get("id", None)

        if (force_refresh or
            product_id is None or
            product_id not in self._cache.component_names):
            self.refresh_products(names=[product],
                                  include_fields=["names", "id"])
            proddict = self._lookup_product_in_cache(product)
            product_id = proddict["id"]

            opts = {'product_id': product_id, 'field': 'component'}
            log.debug("Calling Bug.legal_values with: %s", opts)
            names = self._proxy.Bug.legal_values(opts)["values"]
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
        '''
        A method to create a component in Bugzilla. Takes a dict, with the
        following elements:

        product: The product to create the component in
        component: The name of the component to create
        desription: A one sentence summary of the component
        default_assignee: The bugzilla login (email address) of the initial
                          owner of the component
        default_qa_contact (optional): The bugzilla login of the
                                       initial QA contact
        default_cc: (optional) The initial list of users to be CC'ed on
                               new bugs for the component.
        is_active: (optional) If False, the component is hidden from
                              the component list when filing new bugs.
        '''
        data = data.copy()
        self._component_data_convert(data)
        log.debug("Calling Component.create with: %s", data)
        return self._proxy.Component.create(data)

    def editcomponent(self, data):
        '''
        A method to edit a component in Bugzilla. Takes a dict, with
        mandatory elements of product. component, and initialowner.
        All other elements are optional and use the same names as the
        addcomponent() method.
        '''
        data = data.copy()
        self._component_data_convert(data, update=True)
        log.debug("Calling Component.update with: %s", data)
        return self._proxy.Component.update(data)


    ###################
    # getbug* methods #
    ###################

    def _process_include_fields(self, include_fields, exclude_fields,
                                extra_fields):
        """
        Internal helper to process include_fields lists
        """
        def _convert_fields(_in):
            if not _in:
                return _in

            for newname, oldname in self._get_api_aliases():
                if oldname in _in:
                    _in.remove(oldname)
                    if newname not in _in:
                        _in.append(newname)
            return _in

        ret = {}
        if self._check_version(4, 0):
            if include_fields:
                include_fields = _convert_fields(include_fields)
                if "id" not in include_fields:
                    include_fields.append("id")
                ret["include_fields"] = include_fields
            if exclude_fields:
                exclude_fields = _convert_fields(exclude_fields)
                ret["exclude_fields"] = exclude_fields
        if self._supports_getbug_extra_fields:
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


    # getbug_extra_fields: Extra fields that need to be explicitly
    # requested from Bug.get in order for the data to be returned.
    #
    # As of Dec 2012 it seems like only RH bugzilla actually has behavior
    # like this, for upstream bz it returns all info for every Bug.get()
    _getbug_extra_fields = []
    _supports_getbug_extra_fields = False

    def _getbugs(self, idlist, permissive,
            include_fields=None, exclude_fields=None, extra_fields=None):
        '''
        Return a list of dicts of full bug info for each given bug id.
        bug ids that couldn't be found will return None instead of a dict.
        '''
        oldidlist = idlist
        idlist = []
        for i in oldidlist:
            try:
                idlist.append(int(i))
            except ValueError:
                # String aliases can be passed as well
                idlist.append(i)

        extra_fields = self._listify(extra_fields or [])
        extra_fields += self._getbug_extra_fields

        getbugdata = {"ids": idlist}
        if permissive:
            getbugdata["permissive"] = 1

        getbugdata.update(self._process_include_fields(
            include_fields, exclude_fields, extra_fields))

        log.debug("Calling Bug.get with: %s", getbugdata)
        r = self._proxy.Bug.get(getbugdata)

        if self._check_version(4, 0):
            bugdict = dict([(b['id'], b) for b in r['bugs']])
        else:
            bugdict = dict([(b['id'], b['internals']) for b in r['bugs']])

        ret = []
        for i in idlist:
            found = None
            if i in bugdict:
                found = bugdict[i]
            else:
                # Need to map an alias
                for valdict in bugdict.values():
                    if i in self._listify(valdict.get("alias", None)):
                        found = valdict
                        break

            ret.append(found)

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
        '''Return a Bug object with the full complement of bug data
        already loaded.'''
        data = self._getbug(objid,
            include_fields=include_fields, exclude_fields=exclude_fields,
            extra_fields=extra_fields)
        return Bug(self, dict=data, autorefresh=self.bug_autorefresh)

    def getbugs(self, idlist,
                include_fields=None, exclude_fields=None, extra_fields=None,
                permissive=True):
        '''Return a list of Bug objects with the full complement of bug data
        already loaded. If there's a problem getting the data for a given id,
        the corresponding item in the returned list will be None.'''
        data = self._getbugs(idlist, include_fields=include_fields,
            exclude_fields=exclude_fields, extra_fields=extra_fields,
            permissive=permissive)
        return [(b and Bug(self, dict=b,
                           autorefresh=self.bug_autorefresh)) or None
                for b in data]

    def get_comments(self, idlist):
        '''Returns a dictionary of bugs and comments.  The comments key will
           be empty.  See bugzilla docs for details'''
        return self._proxy.Bug.comments({'ids': idlist})


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
                    boolean_query=None,
                    bug_severity=None,
                    priority=None,
                    target_release=None,
                    target_milestone=None,
                    emailtype=None,
                    booleantype=None,
                    include_fields=None,
                    quicksearch=None,
                    savedsearch=None,
                    savedsearch_sharer_id=None,
                    sub_component=None,
                    tags=None,
                    exclude_fields=None,
                    extra_fields=None):
        """
        Build a query string from passed arguments. Will handle
        query parameter differences between various bugzilla versions.

        Most of the parameters should be self explanatory. However
        if you want to perform a complex query, and easy way is to
        create it with the bugzilla web UI, copy the entire URL it
        generates, and pass it to the static method

        Bugzilla.url_to_query

        Then pass the output to Bugzilla.query()

        For details about the specific argument formats, see the bugzilla docs:
        https://bugzilla.readthedocs.io/en/latest/api/core/v1/bug.html#search-bugs
        """
        if boolean_query or booleantype:
            raise RuntimeError("boolean_query format is no longer supported. "
                "If you need complicated URL queries, look into "
                "query --from-url/url_to_query().")

        query = {
            "alias": alias,
            "product": self._listify(product),
            "component": self._listify(component),
            "version": version,
            "id": bug_id,
            "short_desc": short_desc,
            "bug_status": status,
            "bug_severity": bug_severity,
            "priority": priority,
            "target_release": target_release,
            "target_milestone": target_milestone,
            "tag": self._listify(tags),
            "quicksearch": quicksearch,
            "savedsearch": savedsearch,
            "sharer_id": savedsearch_sharer_id,

            # RH extensions... don't add any more. See comment below
            "sub_components": self._listify(sub_component),
        }

        def add_bool(bzkey, value, bool_id, booltype=None):
            value = self._listify(value)
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
        '''Query bugzilla and return a list of matching bugs.
        query must be a dict with fields like those in in querydata['fields'].
        Returns a list of Bug objects.
        Also see the _query() method for details about the underlying
        implementation.
        '''
        log.debug("Calling Bug.search with: %s", query)
        try:
            r = self._proxy.Bug.search(query)
        except Fault as e:

            # Try to give a hint in the error message if url_to_query
            # isn't supported by this bugzilla instance
            if ("query_format" not in str(e) or
                "RHBugzilla" in str(e.__class__) or
                self._check_version(5, 0)):
                raise
            raise BugzillaError("%s\nYour bugzilla instance does not "
                "appear to support API queries derived from bugzilla "
                "web URL queries." % e)

        log.debug("Query returned %s bugs", len(r['bugs']))
        return [Bug(self, dict=b,
                autorefresh=self.bug_autorefresh) for b in r['bugs']]

    def pre_translation(self, query):
        '''In order to keep the API the same, Bugzilla4 needs to process the
        query and the result. This also applies to the refresh() function
        '''
        pass

    def post_translation(self, query, bug):
        '''In order to keep the API the same, Bugzilla4 needs to process the
        query and the result. This also applies to the refresh() function
        '''
        pass

    def bugs_history_raw(self, bug_ids):
        '''
        Experimental. Gets the history of changes for
        particular bugs in the database.
        '''
        return self._proxy.Bug.history({'ids': bug_ids})


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
        tmp["ids"] = self._listify(ids)

        log.debug("Calling Bug.update with: %s", tmp)
        return self._proxy.Bug.update(tmp)

    def update_tags(self, idlist, tags_add=None, tags_remove=None):
        '''
        Updates the 'tags' field for a bug.
        '''
        tags = {}
        if tags_add:
            tags["add"] = self._listify(tags_add)
        if tags_remove:
            tags["remove"] = self._listify(tags_remove)

        d = {
            "ids": self._listify(idlist),
            "tags": tags,
        }

        log.debug("Calling Bug.update_tags with: %s", d)
        return self._proxy.Bug.update_tags(d)

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
                     comment_tags=None):
        """
        Returns a python dict() with properly formatted parameters to
        pass to update_bugs(). See bugzilla documentation for the format
        of the individual fields:

        https://bugzilla.readthedocs.io/en/latest/api/core/v1/bug.html#create-bug
        """
        ret = {}

        # These are only supported for rhbugzilla
        for key, val in [
            ("fixed_in", fixed_in),
            ("devel_whiteboard", devel_whiteboard),
            ("qa_whiteboard", qa_whiteboard),
            ("internal_whiteboard", internal_whiteboard),
            ("sub_component", sub_component),
        ]:
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
                val = self._listify(val)
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
        s("comment_tags", comment_tags, self._listify)

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

        return ret


    ########################################
    # Methods for working with attachments #
    ########################################

    def _attachment_uri(self, attachid):
        '''Returns the URI for the given attachment ID.'''
        att_uri = self.url.replace('xmlrpc.cgi', 'attachment.cgi')
        att_uri = att_uri + '?id=%s' % attachid
        return att_uri

    def attachfile(self, idlist, attachfile, description, **kwargs):
        '''
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
        '''
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
        if not isinstance(data, bytes):
            data = data.encode(locale.getpreferredencoding())
        kwargs['data'] = Binary(data)

        kwargs['ids'] = self._listify(idlist)

        if 'file_name' not in kwargs and hasattr(f, "name"):
            kwargs['file_name'] = os.path.basename(f.name)
        if 'content_type' not in kwargs:
            ctype = _detect_filetype(getattr(f, "name", None))
            if not ctype:
                ctype = 'application/octet-stream'
            kwargs['content_type'] = ctype

        ret = self._proxy.Bug.add_attachment(kwargs)

        if "attachments" in ret:
            # Up to BZ 4.2
            ret = [int(k) for k in ret["attachments"].keys()]
        elif "ids" in ret:
            # BZ 4.4+
            ret = ret["ids"]

        if isinstance(ret, list) and len(ret) == 1:
            ret = ret[0]
        return ret


    def openattachment(self, attachid):
        '''Get the contents of the attachment with the given attachment ID.
        Returns a file-like object.'''
        attachments = self.get_attachments(None, attachid)
        data = attachments["attachments"][str(attachid)]
        xmlrpcbinary = data["data"]

        ret = BytesIO()
        ret.write(xmlrpcbinary.data)
        ret.name = data["file_name"]
        ret.seek(0)
        return ret

    def updateattachmentflags(self, bugid, attachid, flagname, **kwargs):
        '''
        Updates a flag for the given attachment ID.
        Optional keyword args are:
            status:    new status for the flag ('-', '+', '?', 'X')
            requestee: new requestee for the flag
        '''
        # Bug ID was used for the original custom redhat API, no longer
        # needed though
        ignore = bugid

        flags = {"name": flagname}
        flags.update(kwargs)
        update = {'ids': [int(attachid)], 'flags': [flags]}

        log.debug("Calling Bug.update_attachment(%s)", update)
        return self._proxy.Bug.update_attachment(update)

    def get_attachments(self, ids, attachment_ids,
                        include_fields=None, exclude_fields=None):
        """
        Wrapper for Bug.attachments. One of ids or attachment_ids is required

        :param ids: Get attachments for this bug ID
        :param attachment_ids: Specific attachment ID to get

        https://bugzilla.readthedocs.io/en/latest/api/core/v1/attachment.html#get-attachment
        """
        params = {
            "ids": self._listify(ids) or [],
            "attachment_ids": self._listify(attachment_ids) or [],
        }
        if include_fields:
            params["include_fields"] = self._listify(include_fields)
        if exclude_fields:
            params["exclude_fields"] = self._listify(exclude_fields)

        log.debug("Calling Bug.attachments(%s)", params)
        return self._proxy.Bug.attachments(params)


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
        """"
        Returns a python dict() with properly formatted parameters to
        pass to createbug(). See bugzilla documentation for the format
        of the individual fields:

        https://bugzilla.readthedocs.io/en/latest/api/core/v1/bug.html#update-bug
        """

        localdict = {}
        if blocks:
            localdict["blocks"] = self._listify(blocks)
        if cc:
            localdict["cc"] = self._listify(cc)
        if depends_on:
            localdict["depends_on"] = self._listify(depends_on)
        if groups:
            localdict["groups"] = self._listify(groups)
        if keywords:
            localdict["keywords"] = self._listify(keywords)
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
        if kwargs and args:
            raise BugzillaError("createbug: cannot specify positional "
                                "args=%s with kwargs=%s, must be one or the "
                                "other." % (args, kwargs))
        if args:
            if len(args) > 1 or not isinstance(args[0], dict):
                raise BugzillaError("createbug: positional arguments only "
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
        '''
        Create a bug with the given info. Returns a new Bug object.
        Check bugzilla API documentation for valid values, at least
        product, component, summary, version, and description need to
        be passed.
        '''
        data = self._validate_createbug(*args, **kwargs)
        log.debug("Calling Bug.create with: %s", data)
        rawbug = self._proxy.Bug.create(data)
        return Bug(self, bug_id=rawbug["id"],
                   autorefresh=self.bug_autorefresh)


    ##############################
    # Methods for handling Users #
    ##############################

    def _getusers(self, ids=None, names=None, match=None):
        '''Return a list of users that match criteria.

        :kwarg ids: list of user ids to return data on
        :kwarg names: list of user names to return data on
        :kwarg match: list of patterns.  Returns users whose real name or
            login name match the pattern.
        :raises XMLRPC Fault: Code 51: if a Bad Login Name was sent to the
                names array.
            Code 304: if the user was not authorized to see user they
                requested.
            Code 505: user is logged out and can't use the match or ids
                parameter.

        Available in Bugzilla-3.4+
        '''
        params = {}
        if ids:
            params['ids'] = self._listify(ids)
        if names:
            params['names'] = self._listify(names)
        if match:
            params['match'] = self._listify(match)
        if not params:
            raise BugzillaError('_get() needs one of ids, '
                                ' names, or match kwarg.')

        log.debug("Calling User.get with: %s", params)
        return self._proxy.User.get(params)

    def getuser(self, username):
        '''Return a bugzilla User for the given username

        :arg username: The username used in bugzilla.
        :raises XMLRPC Fault: Code 51 if the username does not exist
        :returns: User record for the username
        '''
        ret = self.getusers(username)
        return ret and ret[0]

    def getusers(self, userlist):
        '''Return a list of Users from .

        :userlist: List of usernames to lookup
        :returns: List of User records
        '''
        userobjs = [User(self, **rawuser) for rawuser in
                    self._getusers(names=userlist).get('users', [])]

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
        '''Return a bugzilla User for the given list of patterns

        :arg pattern: List of patterns to match against.
        :returns: List of User records
        '''
        return [User(self, **rawuser) for rawuser in
                self._getusers(match=pattern).get('users', [])]

    def createuser(self, email, name='', password=''):
        '''Return a bugzilla User for the given username

        :arg email: The email address to use in bugzilla
        :kwarg name: Real name to associate with the account
        :kwarg password: Password to set for the bugzilla account
        :raises XMLRPC Fault: Code 501 if the username already exists
            Code 500 if the email address isn't valid
            Code 502 if the password is too short
            Code 503 if the password is too long
        :return: User record for the username
        '''
        self._proxy.User.create(email, name, password)
        return self.getuser(email)

    def updateperms(self, user, action, groups):
        '''
        A method to update the permissions (group membership) of a bugzilla
        user.

        :arg user: The e-mail address of the user to be acted upon. Can
            also be a list of emails.
        :arg action: add, remove, or set
        :arg groups: list of groups to be added to (i.e. ['fedora_contrib'])
        '''
        groups = self._listify(groups)
        if action == "rem":
            action = "remove"
        if action not in ["add", "remove", "set"]:
            raise BugzillaError("Unknown user permission action '%s'" % action)

        update = {
            "names": self._listify(user),
            "groups": {
                action: groups,
            }
        }

        log.debug("Call User.update with: %s", update)
        return self._proxy.User.update(update)
