# This work is licensed under the GNU GPLv2 or later.
# See the COPYING file in the top-level directory.

from logging import getLogger
import sys
from xmlrpc.client import (Binary, Fault, ProtocolError,
                           ServerProxy, Transport)

from requests import RequestException

from ._backendbase import _BackendBase
from .exceptions import BugzillaError
from ._util import listify


log = getLogger(__name__)


class _BugzillaXMLRPCTransport(Transport):
    def __init__(self, bugzillasession):
        if hasattr(Transport, "__init__"):
            Transport.__init__(self, use_datetime=False)

        self.__bugzillasession = bugzillasession
        self.__bugzillasession.set_xmlrpc_defaults()
        self.__seen_valid_xml = False

        # Override Transport.user_agent
        self.user_agent = self.__bugzillasession.get_user_agent()


    ############################
    # Bugzilla private helpers #
    ############################

    def __request_helper(self, url, request_body):
        """
        A helper method to assist in making a request and parsing the response.
        """
        response = None
        # pylint: disable=try-except-raise
        # pylint: disable=raise-missing-from
        try:
            response = self.__bugzillasession.request(
                "POST", url, data=request_body)

            return self.parse_response(response)
        except RequestException as e:
            if not response:
                raise
            raise ProtocolError(  # pragma: no cover
                url, response.status_code, str(e), response.headers)
        except Fault:
            raise
        except Exception:
            msg = str(sys.exc_info()[1])
            if not self.__seen_valid_xml:
                msg += "\nThe URL may not be an XMLRPC URL: %s" % url
            e = BugzillaError(msg)
            # pylint: disable=attribute-defined-outside-init
            e.__traceback__ = sys.exc_info()[2]
            # pylint: enable=attribute-defined-outside-init
            raise e


    ######################
    # Tranport overrides #
    ######################

    def parse_response(self, response):
        """
        Override Transport.parse_response
        """
        parser, unmarshaller = self.getparser()
        msg = response.text.encode('utf-8')
        try:
            parser.feed(msg)
        except Exception:  # pragma: no cover
            log.debug("Failed to parse this XMLRPC response:\n%s", msg)
            raise

        self.__seen_valid_xml = True
        parser.close()
        return unmarshaller.close()

    def request(self, host, handler, request_body, verbose=0):
        """
        Override Transport.request
        """
        # Setting self.verbose here matches overrided request() behavior
        # pylint: disable=attribute-defined-outside-init
        self.verbose = verbose

        url = "%s://%s%s" % (self.__bugzillasession.get_scheme(),
                host, handler)

        # xmlrpclib fails to escape \r
        request_body = request_body.replace(b'\r', b'&#xd;')

        return self.__request_helper(url, request_body)


class _BugzillaXMLRPCProxy(ServerProxy, object):
    """
    Override of xmlrpc ServerProxy, to insert bugzilla API auth
    into the XMLRPC request data
    """
    def __init__(self, uri, bugzillasession, *args, **kwargs):
        self.__bugzillasession = bugzillasession
        transport = _BugzillaXMLRPCTransport(self.__bugzillasession)
        ServerProxy.__init__(self, uri, transport, *args, **kwargs)

    def _ServerProxy__request(self, methodname, params):
        """
        Overrides ServerProxy _request method
        """
        # params is a singleton tuple, enforced by xmlrpc.client.dumps
        newparams = params and params[0].copy() or {}

        log.debug("XMLRPC call: %s(%s)", methodname, newparams)
        authparams = self.__bugzillasession.get_auth_params()
        authparams.update(newparams)

        # pylint: disable=no-member
        ret = ServerProxy._ServerProxy__request(
            self, methodname, (authparams,))
        # pylint: enable=no-member

        return ret


class _BackendXMLRPC(_BackendBase):
    """
    Internal interface for direct calls to bugzilla's XMLRPC API
    """
    def __init__(self, url, bugzillasession):
        _BackendBase.__init__(self, url, bugzillasession)
        self._xmlrpc_proxy = _BugzillaXMLRPCProxy(url, self._bugzillasession)

    def get_xmlrpc_proxy(self):
        return self._xmlrpc_proxy
    def is_xmlrpc(self):
        return True

    def bugzilla_version(self):
        return self._xmlrpc_proxy.Bugzilla.version()

    def bug_attachment_get(self, attachment_ids, paramdict):
        data = paramdict.copy()
        data["attachment_ids"] = listify(attachment_ids)
        return self._xmlrpc_proxy.Bug.attachments(data)
    def bug_attachment_get_all(self, bug_ids, paramdict):
        data = paramdict.copy()
        data["ids"] = listify(bug_ids)
        return self._xmlrpc_proxy.Bug.attachments(data)
    def bug_attachment_create(self, bug_ids, data, paramdict):
        pdata = paramdict.copy()
        pdata["ids"] = listify(bug_ids)
        if data is not None and "data" not in paramdict:
            pdata["data"] = Binary(data)
        return self._xmlrpc_proxy.Bug.add_attachment(pdata)
    def bug_attachment_update(self, attachment_ids, paramdict):
        data = paramdict.copy()
        data["ids"] = listify(attachment_ids)
        return self._xmlrpc_proxy.Bug.update_attachment(data)

    def bug_comments(self, bug_ids, paramdict):
        data = paramdict.copy()
        data["ids"] = listify(bug_ids)
        return self._xmlrpc_proxy.Bug.comments(data)
    def bug_create(self, paramdict):
        return self._xmlrpc_proxy.Bug.create(paramdict)
    def bug_fields(self, paramdict):
        return self._xmlrpc_proxy.Bug.fields(paramdict)
    def bug_get(self, bug_ids, aliases, paramdict):
        data = paramdict.copy()
        data["ids"] = listify(bug_ids) or []
        data["ids"] += listify(aliases) or []
        return self._xmlrpc_proxy.Bug.get(data)
    def bug_history(self, bug_ids, paramdict):
        data = paramdict.copy()
        data["ids"] = listify(bug_ids)
        return self._xmlrpc_proxy.Bug.history(data)
    def bug_search(self, paramdict):
        return self._xmlrpc_proxy.Bug.search(paramdict)
    def bug_update(self, bug_ids, paramdict):
        data = paramdict.copy()
        data["ids"] = listify(bug_ids)
        return self._xmlrpc_proxy.Bug.update(data)
    def bug_update_tags(self, bug_ids, paramdict):
        data = paramdict.copy()
        data["ids"] = listify(bug_ids)
        return self._xmlrpc_proxy.Bug.update_tags(data)

    def component_create(self, paramdict):
        return self._xmlrpc_proxy.Component.create(paramdict)
    def component_update(self, paramdict):
        return self._xmlrpc_proxy.Component.update(paramdict)

    def externalbugs_add(self, paramdict):
        return self._xmlrpc_proxy.ExternalBugs.add_external_bug(paramdict)
    def externalbugs_update(self, paramdict):
        return self._xmlrpc_proxy.ExternalBugs.update_external_bug(paramdict)
    def externalbugs_remove(self, paramdict):
        return self._xmlrpc_proxy.ExternalBugs.remove_external_bug(paramdict)

    def group_get(self, paramdict):
        return self._xmlrpc_proxy.Group.get(paramdict)

    def product_get(self, paramdict):
        return self._xmlrpc_proxy.Product.get(paramdict)
    def product_get_accessible(self):
        return self._xmlrpc_proxy.Product.get_accessible_products()
    def product_get_enterable(self):
        return self._xmlrpc_proxy.Product.get_enterable_products()
    def product_get_selectable(self):
        return self._xmlrpc_proxy.Product.get_selectable_products()

    def user_create(self, paramdict):
        return self._xmlrpc_proxy.User.create(paramdict)
    def user_get(self, paramdict):
        return self._xmlrpc_proxy.User.get(paramdict)
    def user_login(self, paramdict):
        return self._xmlrpc_proxy.User.login(paramdict)
    def user_logout(self):
        return self._xmlrpc_proxy.User.logout()
    def user_update(self, paramdict):
        return self._xmlrpc_proxy.User.update(paramdict)
