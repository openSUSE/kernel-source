# This work is licensed under the GNU GPLv2 or later.
# See the COPYING file in the top-level directory.

from logging import getLogger

import os
import sys
import urllib.parse

import requests


log = getLogger(__name__)


class _BugzillaSession(object):
    """
    Class to handle the backend agnostic 'requests' setup
    """
    def __init__(self, url, user_agent,
            sslverify, cert, tokencache, api_key,
            is_redhat_bugzilla,
            requests_session=None):
        self._url = url
        self._user_agent = user_agent
        self._scheme = urllib.parse.urlparse(url)[0]
        self._tokencache = tokencache
        self._api_key = api_key
        self._is_xmlrpc = False
        self._use_auth_bearer = False

        if self._scheme not in ["http", "https"]:
            raise Exception("Invalid URL scheme: %s (%s)" % (
                self._scheme, url))

        self._session = requests_session
        if not self._session:
            self._session = requests.Session()

        if cert:
            self._session.cert = cert
        if sslverify is False:
            self._session.verify = False
        self._session.headers["User-Agent"] = self._user_agent

        if is_redhat_bugzilla and self._api_key:
            self._use_auth_bearer = True
            self._session.headers["Authorization"] = (
                "Bearer %s" % self._api_key)

    def _get_timeout(self):
        # Default to 5 minutes. This is longer than bugzilla.redhat.com's
        # apparent 3 minute timeout so shouldn't affect legitimate usage,
        # but saves us from indefinite hangs
        DEFAULT_TIMEOUT = 300
        envtimeout = os.environ.get("PYTHONBUGZILLA_REQUESTS_TIMEOUT")
        return float(envtimeout or DEFAULT_TIMEOUT)

    def set_rest_defaults(self):
        self._session.headers["Content-Type"] = "application/json"
    def set_xmlrpc_defaults(self):
        self._is_xmlrpc = True
        self._session.headers["Content-Type"] = "text/xml"

    def get_user_agent(self):
        return self._user_agent
    def get_scheme(self):
        return self._scheme

    def get_auth_params(self):
        # bugzilla.redhat.com will error if there's auth bits in params
        # when Authorization header is used
        if self._use_auth_bearer:
            return {}

        # Don't add a token to the params list if an API key is set.
        # Keeping API key solo means bugzilla will definitely fail
        # if the key expires. Passing in a token could hide that
        # fact, which could make it confusing to pinpoint the issue.
        if self._api_key:
            # Bugzilla 5.0 only supports api_key as a query parameter.
            # Bugzilla 5.1+ takes it as a X-BUGZILLA-API-KEY header as well,
            # with query param taking preference.
            return {"Bugzilla_api_key": self._api_key}

        token = self._tokencache.get_value(self._url)
        if token:
            return {"Bugzilla_token": token}

        return {}

    def get_requests_session(self):
        return self._session

    def request(self, *args, **kwargs):
        timeout = self._get_timeout()
        if "timeout" not in kwargs:
            kwargs["timeout"] = timeout

        response = self._session.request(*args, **kwargs)

        if self._is_xmlrpc:
            # Yes this still appears to matter for properly decoding unicode
            # code points in bugzilla.redhat.com content
            response.encoding = "UTF-8"

        try:
            response.raise_for_status()
        except Exception as e:
            # Scrape the api key out of the returned exception string
            message = str(e).replace(self._api_key or "", "")
            raise type(e)(message).with_traceback(sys.exc_info()[2])

        return response
