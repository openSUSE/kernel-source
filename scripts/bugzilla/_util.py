# This work is licensed under the GNU GPLv2 or later.
# See the COPYING file in the top-level directory.


def listify(val):
    """Ensure that value is either None or a list, converting single values
    into 1-element lists"""
    if val is None:
        return val
    if isinstance(val, list):
        return val
    return [val]
