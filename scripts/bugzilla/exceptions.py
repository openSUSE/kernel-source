# This work is licensed under the GNU GPLv2 or later.
# See the COPYING file in the top-level directory.


class BugzillaError(Exception):
    """
    Error raised in the Bugzilla client code.
    """
    @staticmethod
    def get_bugzilla_error_string(exc):
        """
        Helper to return the bugzilla instance error message from an
        XMLRPC Fault, or any other exception type that's raised from bugzilla
        interaction
        """
        return getattr(exc, "faultString", str(exc))

    @staticmethod
    def get_bugzilla_error_code(exc):
        """
        Helper to return the bugzilla instance error code from an
        XMLRPC Fault, or any other exception type that's raised from bugzilla
        interaction
        """
        for propname in ["faultCode", "code"]:
            if hasattr(exc, propname):
                return getattr(exc, propname)
        return None

    def __init__(self, message, code=None):
        """
        :param code: The error code from the remote bugzilla instance. Only
            set if the error came directly from the remove bugzilla
        """
        self.code = code
        if self.code:
            message += " (code=%s)" % self.code
        Exception.__init__(self, message)
