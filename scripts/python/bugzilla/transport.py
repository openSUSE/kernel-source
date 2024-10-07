# This program is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by the
# Free Software Foundation; either version 2 of the License, or (at your
# option) any later version.  See http://www.gnu.org/copyleft/gpl.html for
# the full text of the license.

from logging import getLogger
import sys

# pylint: disable=import-error
if sys.version_info[0] >= 3:
    from configparser import SafeConfigParser
    from urllib.parse import urlparse  # pylint: disable=no-name-in-module
    from xmlrpc.client import Fault, ProtocolError, ServerProxy, Transport
else:
    from ConfigParser import SafeConfigParser
    from urlparse import urlparse
    from xmlrpclib import Fault, ProtocolError, ServerProxy, Transport
# pylint: enable=import-error

import requests


log = getLogger(__name__)


class BugzillaError(Exception):
    '''Error raised in the Bugzilla client code.'''
    pass


class _BugzillaTokenCache(object):
    """
    Cache for tokens, including, with apologies for the duplicative
    terminology, both Bugzilla Tokens and API Keys.
    """

    def __init__(self, uri, tokenfilename):
        self.tokenfilename = tokenfilename
        self.tokenfile = SafeConfigParser()
        self.domain = urlparse(uri)[1]

        if self.tokenfilename:
            self.tokenfile.read(self.tokenfilename)

        if self.domain not in self.tokenfile.sections():
            self.tokenfile.add_section(self.domain)

    @property
    def value(self):
        if self.tokenfile.has_option(self.domain, 'token'):
            return self.tokenfile.get(self.domain, 'token')
        else:
            return None

    @value.setter
    def value(self, value):
        if self.value == value:
            return

        if value is None:
            self.tokenfile.remove_option(self.domain, 'token')
        else:
            self.tokenfile.set(self.domain, 'token', value)

        if self.tokenfilename:
            with open(self.tokenfilename, 'w') as tokenfile:
                log.debug("Saving to tokenfile")
                self.tokenfile.write(tokenfile)

    def __repr__(self):
        return '<Bugzilla Token Cache :: %s>' % self.value


class _BugzillaServerProxy(ServerProxy, object):
    def __init__(self, uri, tokenfile, *args, **kwargs):
        super(_BugzillaServerProxy, self).__init__(uri, *args, **kwargs)
        self.token_cache = _BugzillaTokenCache(uri, tokenfile)
        self.api_key = None

    def use_api_key(self, api_key):
        self.api_key = api_key

    def clear_token(self):
        self.token_cache.value = None

    def _ServerProxy__request(self, methodname, params):
        if len(params) == 0:
            params = ({}, )

        if self.api_key is not None:
            if 'Bugzilla_api_key' not in params[0]:
                params[0]['Bugzilla_api_key'] = self.api_key
        elif self.token_cache.value is not None:
            if 'Bugzilla_token' not in params[0]:
                params[0]['Bugzilla_token'] = self.token_cache.value

        # pylint: disable=no-member
        ret = super(_BugzillaServerProxy,
                self)._ServerProxy__request(methodname, params)
        # pylint: enable=no-member

        if isinstance(ret, dict) and 'token' in ret.keys():
            self.token_cache.value = ret.get('token')
        return ret


class _RequestsTransport(Transport):
    user_agent = 'Python/Bugzilla'

    def __init__(self, url, cookiejar=None,
                 sslverify=True, sslcafile=None, debug=True, cert=None):
        if hasattr(Transport, "__init__"):
            Transport.__init__(self, use_datetime=False)

        self.verbose = debug
        self._cookiejar = cookiejar

        # transport constructor needs full url too, as xmlrpc does not pass
        # scheme to request
        self.scheme = urlparse(url)[0]
        if self.scheme not in ["http", "https"]:
            raise Exception("Invalid URL scheme: %s (%s)" % (self.scheme, url))

        self.use_https = self.scheme == 'https'

        self.request_defaults = {
            'cert': sslcafile if self.use_https else None,
            'cookies': cookiejar,
            'verify': sslverify,
            'headers': {
                'Content-Type': 'text/xml',
                'User-Agent': self.user_agent,
            }
        }

        # Using an explicit Session, rather than requests.get, will use
        # HTTP KeepAlive if the server supports it.
        self.session = requests.Session()
        if cert:
            self.session.cert = cert

    def parse_response(self, response):
        """ Parse XMLRPC response """
        parser, unmarshaller = self.getparser()
        parser.feed(response.text.encode('utf-8'))
        parser.close()
        return unmarshaller.close()

    def _request_helper(self, url, request_body):
        """
        A helper method to assist in making a request and provide a parsed
        response.
        """
        response = None
        try:
            response = self.session.post(
                url, data=request_body, **self.request_defaults)

            # We expect utf-8 from the server
            response.encoding = 'UTF-8'

            # update/set any cookies
            if self._cookiejar is not None:
                for cookie in response.cookies:
                    self._cookiejar.set_cookie(cookie)

                if self._cookiejar.filename is not None:
                    # Save is required only if we have a filename
                    self._cookiejar.save()

            log.debug(response.text)
            response.raise_for_status()
            return self.parse_response(response)
        except requests.RequestException as e:
            if not response:
                raise
            raise ProtocolError(
                url, response.status_code, str(e), response.headers)
        except Fault:
            raise
        except Exception:
            e = BugzillaError(str(sys.exc_info()[1]))
            # pylint: disable=attribute-defined-outside-init
            e.__traceback__ = sys.exc_info()[2]
            # pylint: enable=attribute-defined-outside-init
            raise e

    def request(self, host, handler, request_body, verbose=0):
        self.verbose = verbose
        url = "%s://%s%s" % (self.scheme, host, handler)

        # xmlrpclib fails to escape \r
        request_body = request_body.replace(b'\r', b'&#xd;')

        return self._request_helper(url, request_body)
