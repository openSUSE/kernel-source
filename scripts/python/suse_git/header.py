#!/usr/bin/env python
# vim: sw=4 ts=4 et si:

import sys
import re
from optparse import OptionParser
from . import patch
from StringIO import StringIO

diffstart = re.compile("^(---|\*\*\*|Index:|\+\+\+)[ \t][^ \t]\S+/|^diff -")
tag_regex = re.compile("(\S+):[ \t]*(.*)")

tag_map = {
    'Patch-mainline' : {
        'required' : True,
        'accepted' : [
            {
                # In mainline repo, tagged for release
                'name' : 'Version',
                'match': 'v?(\d+\.)+\d+(-rc\d+)?\s*$',
                'requires' : [ 'Git-commit' ],
                'excludes' : [ 'Git-repo' ],
            }, {    # In mainline repo but not tagged yet
                'name' : 'Version',
                'match': 'v?(\d+\.)+\d+(-rc\d+)?\s+or\s+v?(\d+\.)+\d+(-rc\d+)?\s+\(next release\)\s*$',
                'requires' : [ 'Git-commit' ],
                'excludes' : [ 'Git-repo' ],
            }, {
                # Queued in subsystem maintainer repo
                'name' : 'Queued',
                'match' : 'Queued(.*)',
                'requires' : [ 'Git-commit', 'Git-repo' ],
            }, {
                # Depends on another non-upstream patch
                'name' : 'Depends',
                'match' : 'Depends on\s+.+',
                'excludes' : [ 'Git-commit', 'Git-repo' ],
            }, {
                # No, typically used for patches that have review issues
                # but are not fundamentally rejected
                'name' : 'No',
                'match' : 'No,?\s+.+',
                'excludes' : [ 'Git-commit', 'Git-repo' ],
            }, {
                # Never, typically used for patches that have been rejected
                # for upstream inclusion but still have a compelling reason
                # for inclusion in a SUSE release or are otherwise
                # inappropriate for upstream inclusion (packaging, kABI,
                # SLES-only feature.)
                'name' : 'Never',
                'match' : 'Never,?\s+.+',
                'excludes' : [ 'Git-commit', 'Git-repo' ],
            }, {
                # Submitted upstream.  Description should provide either
                # a date and a mailing list or a URL to an archived post.
                'name' : 'Submitted',
                'match' : 'Submitted,?\s+.+',
                'excludes' : [ 'Git-commit', 'Git-repo' ],
            }, {
                # Should be used rarely.  Description should provide
                # reason for the patch not being accepted upstream.
                'name' : 'Not yet',
                'match' : 'Not yet,?\s+.+',
                'excludes' : [ 'Git-commit', 'Git-repo' ],
            }, {
                'match' : 'Submitted\s*$',
                'error' : 'Requires a description: <date> <list> or <url>',
                'excludes' : [ 'Git-commit', 'Git-repo' ],
            }, {
                'match' : 'Yes\s+$',
                'error' : 'Exact version required',
            }, {
                'match' : 'Yes.*(\d+\.)+\d+',
                'error' : '`Yes\' keyword is invalid',
                'excludes' : [ 'Git-commit', 'Git-repo' ],
            }, {
                'match' : '(Never|Not yet|No)\s*$',
                'error' : 'Requires a reason',
                'excludes' : [ 'Git-commit', 'Git-repo' ],
            },
        ],
        'requires_any' : [ 'Signed-off-by:SUSE', 'Acked-by:SUSE', 'From:SUSE',
                           'Reviewed-by:SUSE' ],
    },
    'Git-commit' : {
        'multi' : True,
        'accepted' : [
            {
                # 40-character SHA1 hash with optional partial tag
                'match' : '([0-9a-fA-F]){40}(\s+\(partial\))?',
            }
        ],
        'requires_any' : [ 'Patch-mainline:Version', 'Patch-mainline:Queued' ],
        'error' : "requires full SHA1 hash and optional (partial) tag",
    },
    'Git-repo' : {
        'accepted' : [
            {
                # Weak match for URL.  Abbreviated names are not acceptable.
                'match' : '.*/.*',
            }
        ],
        'requires' : [ 'Git-commit' ],
        'error' : "must contain URL pointing to repository containing the commit (and branch, if not master)",
    },
    'Signed-off-by' : {
        'multi' : True,
        'accepted' : [
            {
                'name' : 'SUSE',
                'match' : '.*@(suse\.(com|de|cz)|novell.com)',
            },
            {
                'match' : '.*',
            }
        ],
    },
    'Acked-by' : {
        'multi' : True,
        'accepted' : [
            {
                'name' : 'SUSE',
                'match' : '.*@(suse\.(com|de|cz)|novell.com)',
            },
            {
                'match' : '.*',
            }
        ],
    },
    'Reviewed-by' : {
        'multi' : True,
        'accepted' : [
            {
                'name' : 'SUSE',
                'match' : '.*@(suse\.(com|de|cz)|novell.com)',
            },
            {
                'match' : '.*',
            }
        ],
    },
    'From' : {
        'multi' : True,
        'accepted' : [
            {
                'name' : 'SUSE',
                'match' : '.*@(suse\.(com|de|cz)|novell.com)',
            },
            {
                'match' : '.*',
            }
        ],
    },
#    'References' : {
#        'required' : True,
#        'accepted' : [
#            {
#                'match' : '(([a-z]+)#\d+),*\s*)+',
#            },
#        ],
#        'error' : "must contain list of references",
#    }
}

class ValidationError(patch.ValidationError):
    def __init__(self, name, msg):
        super(ValidationError, self).__init__(msg)
        self.name = name

class FormatError(ValidationError):
    def __init__(self, name, value, error=None):
        name = name.capitalize()
        if error is None:
            error = "invalid value"
        msg = "%s: `%s': %s." % (name, value, error)
        super(FormatError, self).__init__(name, msg)

class MissingTagError(ValidationError):
    def __init__(self, tag, requires):
        if not tag:
            tag = Tag("Policy", None)
        msg = "%s%s requires %s%s." % (tag.name, \
                    " (%s)" % tag.tagtype if tag.tagtype else "", \
                    requires[0], \
                    " (%s)" % requires[1] if requires[1] else "")
        self.target = [requires]
        super(MissingTagError, self).__init__(tag.name, msg)

class MissingMultiTagError(MissingTagError):
    def __init__(self, tag, requires):
        if not tag:
            tag = Tag("Policy", None)
        msg = "%s%s requires %s." % (tag.name, \
                " (%s)" % tag.tagtype if tag.tagtype else "", \
                " or ".join(["%s%s" % (req[0], \
                    " (%s)" % req[1] if req[1] else "") for req in requires]))
        self.target = requires
        super(MissingTagError, self).__init__(tag.name, msg)

class ExcludedTagError(ValidationError):
    def __init__(self, tag, excludes):
        msg = "%s%s excludes %s%s." % (tag.name,
                " (%s)" % tag.tagtype if tag.tagtype else "", \
                excludes[0], \
                " (%s)" % excludes[1] if excludes[1] else "")
        super(ExcludedTagError, self).__init__(tag.name, msg)

class DuplicateTagError(ValidationError):
    def __init__(self, name):
        name = name.capitalize()
        msg = "%s must only be used once, even if it is identical." % name
        super(DuplicateTagError, self).__init__(name, msg)
    pass

class EmptyTagError(ValidationError):
    def __init__(self, name):
        name = name.capitalize()
        msg = "%s: Value cannot be empty." % name
        super(EmptyTagError, self).__init__(name, msg)

class HeaderException(patch.PatchException):
    def tag_is_missing(self, name):
        try:
            for err in self._errors:
                if isinstance(err, MissingTagError):
                    for tag in err.target:
                        if tag[0].lower() == name.lower():
                            return True
        except KeyError, e:
            pass

        return False

class Tag:
    def __init__(self, name, value):
        self.name = name.lower().capitalize()
        self.value = value
        self.tagtype = None
        self.valid = False

    def __str__(self):
        return "%s: %s" % (self.name, self.value)

    def __repr__(self):
        type = "<none>"
        if self.tagtype:
            type = self.tagtype
        valid = "No"
        if self.valid:
            valid = "Yes"
        return "<Tag: name=%s value='%s' type='%s' valid='%s'>" % \
                (self.name, self.value, type, valid)

    def match_req(self, req):
        if self.name == req[0]:
            if req[1] is None:
                if self.valid:
                    return True
            elif self.tagtype == req[1] and self.valid:
                return True
        return False

def handle_requires(tag, rules, target):
    if isinstance(tag, str):
        tag = Tag(tag, None)
    for req in rules:
        s = req.split(':')
        if len(s) > 1:
            new_req = (s[0], s[1])
        else:
            new_req = (s[0], None)

        if not tag in target:
            target[tag] = []
        target[tag].append(new_req)

class HeaderChecker(patch.PatchChecker):
    def __init__(self):
        patch.PatchChecker.__init__(self)

    def do_patch(self, stream):
        requires = {}
        requires_any = {}
        excludes = {}
        tags = []
        errors = []

        if isinstance(stream, str):
            stream = StringIO(stream)

        for line in stream.readlines():
            if diffstart.match(line):
                break

            m = tag_regex.match(line)
            if m:
                tag = Tag(m.group(1), m.group(2))

                if tag.name not in tag_map:
                    continue;

                if re.match("\s*$", tag.value):
                    errors.append(EmptyTagError(tag.name))
                    continue

                mapping = tag_map[tag.name]

                try:
                    multi = mapping['multi']
                except KeyError, e:
                    multi = False

                for t in tags:
                    if tag.name == t.name and not multi:
                        errors.append(DuplicateTagError(tag.name))
                        continue

                # No rules to process
                if 'accepted' not in mapping:
                    tags.append(tag)
                    continue

                match = False
                error = False
                for rule in mapping['accepted']:
                    if not re.match(rule['match'], tag.value, re.I):
                        continue

                    match = True

                    if 'name' in rule:
                        tag.tagtype = rule['name']

                    if 'error' in rule:
                        error = True
                        errors.append(FormatError(tag.name, tag.value,
                                                  rule['error']))
                        break

                    tag.valid = True

                    if 'requires' in rule:
                        handle_requires(tag, rule['requires'], requires)
                    if 'requires_any' in rule:
                        handle_requires(tag, rule['requires_any'], requires_any)
                    if 'excludes' in rule:
                        handle_requires(tag, rule['excludes'], excludes)
                    break

                tags.append(tag)

                if tag.valid:
                    if 'requires' in mapping:
                        handle_requires(tag.name, mapping['requires'], requires)
                    if 'requires_any' in mapping:
                        handle_requires(tag.name, mapping['requires_any'],
                                        requires_any)
                    if 'excludes' in mapping:
                        handle_requires(tag.name, mapping['excludes'], excludes)


                if error:
                    continue

                if not match:
                    errmsg = None
                    if 'error' in mapping:
                        errmsg = mapping['error']
                    errors.append(FormatError(tag.name, tag.value, errmsg))
                    continue

        if requires:
            for reqtag in requires:
                for req in requires[reqtag]:
                    found = False
                    for tag in tags:
                        found = tag.match_req(req)
                        if found:
                            break
                    if not found:
                        errors.append(MissingTagError(reqtag, req))

        if requires_any:
            for reqtag in requires_any:
                found = False
                for req in requires_any[reqtag]:
                    for tag in tags:
                        found = tag.match_req(req)
                        if found:
                            break
                    if found:
                        break
                if not found:
                    errors.append(MissingMultiTagError(reqtag,
                                                       requires_any[reqtag]))

        if excludes:
            for reqtag in excludes:
                for req in excludes[reqtag]:
                    found = False
                    for tag in tags:
                        found = tag.match_req(req)
                        if found:
                            break
                    if found:
                        errors.append(ExcludedTagError(reqtag, req))

        for entry in tag_map:
            if 'required' in tag_map[entry]:
                found = False
                for tag in tags:
                    if entry == tag.name:
                        found = True
                if not found:
                    errors.append(MissingTagError(None, (entry, None)))

        if errors:
            raise HeaderException(errors)

Checker = HeaderChecker
