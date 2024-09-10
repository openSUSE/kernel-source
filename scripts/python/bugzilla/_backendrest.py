# This work is licensed under the GNU GPLv2 or later.
# See the COPYING file in the top-level directory.

import base64
import json
import logging
import os

from ._backendbase import _BackendBase
from .exceptions import BugzillaError
from ._util import listify


log = logging.getLogger(__name__)


def _update_key(indict, updict, key):
    if key not in indict:
        indict[key] = {}
    indict[key].update(updict.get(key, {}))


class _BackendREST(_BackendBase):
    """
    Internal interface for direct calls to bugzilla's REST API
    """
    def __init__(self, url, bugzillasession):
        _BackendBase.__init__(self, url, bugzillasession)
        self._bugzillasession.set_rest_defaults()


    #########################
    # Internal REST helpers #
    #########################

    def _handle_response(self, text):
        try:
            ret = dict(json.loads(text))
        except Exception:  # pragma: no cover
            log.debug("Failed to parse REST response. Output is:\n%s", text)
            raise

        if ret.get("error", False):
            raise BugzillaError(ret["message"], code=ret["code"])
        return ret

    def _op(self, method, apiurl, paramdict=None):
        fullurl = os.path.join(self._url, apiurl.lstrip("/"))
        log.debug("Bugzilla REST %s %s params=%s", method, fullurl, paramdict)

        data = None
        authparams = self._bugzillasession.get_auth_params()
        if method == "GET":
            authparams.update(paramdict or {})
        else:
            data = json.dumps(paramdict or {})

        response = self._bugzillasession.request(method, fullurl, data=data,
                params=authparams)
        return self._handle_response(response.text)

    def _get(self, *args, **kwargs):
        return self._op("GET", *args, **kwargs)
    def _put(self, *args, **kwargs):
        return self._op("PUT", *args, **kwargs)
    def _post(self, *args, **kwargs):
        return self._op("POST", *args, **kwargs)


    #######################
    # API implementations #
    #######################

    def get_xmlrpc_proxy(self):
        raise BugzillaError("You are using the bugzilla REST API, "
                "so raw XMLRPC access is not provided.")
    def is_rest(self):
        return True

    def bugzilla_version(self):
        return self._get("/version")

    def bug_create(self, paramdict):
        return self._post("/bug", paramdict)
    def bug_fields(self, paramdict):
        return self._get("/field/bug", paramdict)
    def bug_get(self, bug_ids, aliases, paramdict):
        data = paramdict.copy()
        data["id"] = listify(bug_ids)
        data["alias"] = listify(aliases)
        ret = self._get("/bug", data)
        return ret

    def bug_attachment_get(self, attachment_ids, paramdict):
        # XMLRPC supported mutiple fetch at once, but not REST
        ret = {}
        for attid in listify(attachment_ids):
            out = self._get("/bug/attachment/%s" % attid, paramdict)
            _update_key(ret, out, "attachments")
            _update_key(ret, out, "bugs")
        return ret

    def bug_attachment_get_all(self, bug_ids, paramdict):
        # XMLRPC supported mutiple fetch at once, but not REST
        ret = {}
        for bugid in listify(bug_ids):
            out = self._get("/bug/%s/attachment" % bugid, paramdict)
            _update_key(ret, out, "attachments")
            _update_key(ret, out, "bugs")
        return ret

    def bug_attachment_create(self, bug_ids, data, paramdict):
        if data is not None and "data" not in paramdict:
            paramdict["data"] = base64.b64encode(data).decode("utf-8")
        paramdict["ids"] = listify(bug_ids)
        return self._post("/bug/%s/attachment" % paramdict["ids"][0],
                paramdict)

    def bug_attachment_update(self, attachment_ids, paramdict):
        paramdict["ids"] = listify(attachment_ids)
        return self._put("/bug/attachment/%s" % paramdict["ids"][0], paramdict)

    def bug_comments(self, bug_ids, paramdict):
        # XMLRPC supported mutiple fetch at once, but not REST
        ret = {}
        for bugid in bug_ids:
            out = self._get("/bug/%s/comment" % bugid, paramdict)
            _update_key(ret, out, "bugs")
        return ret
    def bug_history(self, bug_ids, paramdict):
        # XMLRPC supported mutiple fetch at once, but not REST
        ret = {"bugs": []}
        for bugid in bug_ids:
            out = self._get("/bug/%s/history" % bugid, paramdict)
            ret["bugs"].extend(out.get("bugs", []))
        return ret

    def bug_search(self, paramdict):
        return self._get("/bug", paramdict)
    def bug_update(self, bug_ids, paramdict):
        data = paramdict.copy()
        data["ids"] = listify(bug_ids)
        return self._put("/bug/%s" % data["ids"][0], data)
    def bug_update_tags(self, bug_ids, paramdict):
        raise BugzillaError("No REST API available for bug_update_tags")

    def component_create(self, paramdict):
        return self._post("/component", paramdict)
    def component_update(self, paramdict):
        if "ids" in paramdict:
            apiurl = str(listify(paramdict["ids"])[0])  # pragma: no cover
        if "names" in paramdict:
            apiurl = ("%(product)s/%(component)s" %
                    listify(paramdict["names"])[0])
        return self._put("/component/%s" % apiurl, paramdict)

    def externalbugs_add(self, paramdict):  # pragma: no cover
        raise BugzillaError(
            "No REST API available yet for externalbugs_add")
    def externalbugs_remove(self, paramdict):  # pragma: no cover
        raise BugzillaError(
            "No REST API available yet for externalbugs_remove")
    def externalbugs_update(self, paramdict):  # pragma: no cover
        raise BugzillaError(
            "No REST API available yet for externalbugs_update")

    def group_get(self, paramdict):
        return self._get("/group", paramdict)

    def product_get(self, paramdict):
        return self._get("/product/get", paramdict)
    def product_get_accessible(self):
        return self._get("/product_accessible")
    def product_get_enterable(self):
        return self._get("/product_enterable")
    def product_get_selectable(self):
        return self._get("/product_selectable")

    def user_create(self, paramdict):
        return self._post("/user", paramdict)
    def user_get(self, paramdict):
        return self._get("/user", paramdict)
    def user_login(self, paramdict):
        return self._get("/login", paramdict)
    def user_logout(self):
        return self._get("/logout")
    def user_update(self, paramdict):
        urlid = None
        if "ids" in paramdict:
            urlid = listify(paramdict["ids"])[0]  # pragma: no cover
        if "names" in paramdict:
            urlid = listify(paramdict["names"])[0]
        return self._put("/user/%s" % urlid, paramdict)
