#!/usr/bin/env python3
# vim: sw=4 ts=4 et si:

import re
from . import patch
from io import StringIO

diffstart = re.compile("^(---|\*\*\*|Index:|\+\+\+)[ \t][^ \t]\S+/|^diff -")
tag_regex = re.compile("(\S+):[ \t]*(.*)")

tag_map = {
    'Patch-mainline' : {
        'required' : True,
        'required_on_kabi' : False,
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
                'error' : "Please use 'Not yet' or 'Never'",
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
                # Catch a frequent misuse of 'Not yet'.
                'match' : 'Not yet,\s+submitted',
                'error' : "Please use 'Submitted'",
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
    'Alt-commit' : {
        'multi' : True,
        'accepted' : [
            {
                # 40-character SHA1 hash
                'match' : '([0-9a-fA-F]){40}$',
            }
        ],
        'error' : "requires one full SHA1 hash without trailing spaces",
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
                'match' : '.*@suse\.(com|de|cz)',
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
                'match' : '.*@suse\.(com|de|cz)',
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
                'match' : '.*@suse\.(com|de|cz)',
            },
            {
                'match' : '.*',
            }
        ],
    },
    'From' : {
        'multi' : True,
        'required' : True,
        'accepted' : [
            {
                'name' : 'SUSE',
                'match' : '.*@suse\.(com|de|cz)',
            },
            {
                'match' : '.*',
            }
        ],
    },
    'Subject' : {
        'required' : True,
        'accepted' :  [
            {
                'match' : '\S+',
            },
        ],
    },
    'References' : {
        'required' : True,
        'required_on_update' : False,
        'multi' : True,
        'accepted' : [
            {
                'name' : 'SUSE',
                'match' : '((bsc|boo|bnc|fate)#\d+|jsc#\w+-\d+)',
            },
            {
                'match' : '\S+',
            },
        ],
        'error' : "must contain list of references",
     # Enable to require real References tags
     #   'requires' : ['References:SUSE'],
    }
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
                    requires['name'], \
                    " (%s)" % requires['type'] if 'type' in requires else "")
        self.target = [requires]
        super(MissingTagError, self).__init__(tag.name, msg)

class MissingMultiTagError(MissingTagError):
    def __init__(self, tag, requires):
        if not tag:
            tag = Tag("Policy", None)
        msg = "%s%s requires %s." % (tag.name, \
                " (%s)" % tag.tagtype if tag.tagtype else "", \
                " or ".join(["%s%s" % (req['name'], \
                    " (%s)" % req['type'] if 'type' in req else "") for req in requires]))
        self.target = requires
        super(MissingTagError, self).__init__(tag.name, msg)

class ExcludedTagError(ValidationError):
    def __init__(self, tag, excludes):
        msg = "%s%s excludes %s%s." % (tag.name,
                " (%s)" % tag.tagtype if tag.tagtype else "", \
                excludes['name'], \
                " (%s)" % excludes['type'] if 'type' in excludes else "")
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
                        if tag['name'].lower() == name.lower():
                            return True
        except KeyError:
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
        tagtype = "<none>"
        if self.tagtype:
            tagtype = self.tagtype
        valid = "No"
        if self.valid:
            valid = "Yes"
        return "<Tag: name=%s value='%s' type='%s' valid='%s'>" % \
                (self.name, self.value, tagtype, valid)

    def match_req(self, req):
        if self.name == req['name']:
            if 'type' not in req or self.tagtype == req['type']:
                if self.valid:
                    return True
        return False

class HeaderChecker(patch.PatchChecker):
    def __init__(self, stream, updating=False, filename="<unknown>"):
        patch.PatchChecker.__init__(self)
        self.updating = updating
        self.filename = filename
        self.kabi = re.match("^patches[.]kabi/", self.filename)

        if isinstance(stream, str):
            stream = StringIO(stream)
        self.stream = stream

        self.requires = {}
        self.requires_any = {}
        self.excludes = {}
        self.tags = []
        self.errors = []

        self.do_patch()

    def get_rulename(self, ruleset, rulename):
        if rulename in ruleset:
            if self.kabi:
                kabi_rule = "%s_on_kabi" % rulename
                if kabi_rule in ruleset:
                    return kabi_rule
            if self.updating:
                updating_rule = "%s_on_update" % rulename
                if updating_rule in ruleset:
                    return updating_rule
            return rulename
        return None

    def handle_requires(self, tag, ruleset, rulename):
        target = getattr(self, rulename)

        rulename = self.get_rulename(ruleset, rulename)
        if not rulename:
            return

        if isinstance(tag, str):
            tag = Tag(tag, None)

        for req in ruleset[rulename]:
            s = req.split(':')
            new_req = {
                'name' : s[0]
            }
            if len(s) > 1:
                new_req['type'] = s[1]
            if not tag in target:
                target[tag] = []
            target[tag].append(new_req)

    def do_patch(self):
        for line in self.stream.readlines():
            if diffstart.match(line):
                break

            m = tag_regex.match(line)
            if m:
                tag = Tag(m.group(1), m.group(2))

                if tag.name not in tag_map:
                    continue;

                if re.match("\s*$", tag.value):
                    self.errors.append(EmptyTagError(tag.name))
                    continue

                mapping = tag_map[tag.name]

                try:
                    multi = mapping['multi']
                except KeyError:
                    multi = False

                for t in self.tags:
                    if tag.name == t.name and not multi:
                        self.errors.append(DuplicateTagError(tag.name))
                        continue

                # No rules to process
                if 'accepted' not in mapping:
                    self.tags.append(tag)
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
                        self.errors.append(FormatError(tag.name, tag.value,
                                                  rule['error']))
                        break

                    tag.valid = True

                    # Handle rule-level dependencies
                    self.handle_requires(tag, rule, 'requires')
                    self.handle_requires(tag, rule, 'requires_any')
                    self.handle_requires(tag, rule, 'excludes')
                    break

                # Handle tag-level dependencies
                if tag.valid:
                    self.handle_requires(tag, mapping, 'requires')
                    self.handle_requires(tag, mapping, 'requires_any')
                    self.handle_requires(tag, mapping, 'excludes')

                self.tags.append(tag)

                if error:
                    continue

                if not match:
                    errmsg = None
                    if 'error' in mapping:
                        errmsg = mapping['error']
                    self.errors.append(FormatError(tag.name, tag.value, errmsg))
                    continue

        for reqtag in self.requires:
            for req in self.requires[reqtag]:
                found = False
                for tag in self.tags:
                    found = tag.match_req(req)
                    if found:
                        break
                if not found:
                    self.errors.append(MissingTagError(reqtag, req))

        for reqtag in self.requires_any:
            found = False
            for req in self.requires_any[reqtag]:
                for tag in self.tags:
                    found = tag.match_req(req)
                    if found:
                        break
                if found:
                    break
            if not found:
                self.errors.append(
                        MissingMultiTagError(reqtag, self.requires_any[reqtag]))

        for reqtag in self.excludes:
            for req in self.excludes[reqtag]:
                found = False
                for tag in self.tags:
                    found = tag.match_req(req)
                    if found:
                        break
                if found:
                    self.errors.append(ExcludedTagError(reqtag, req))

        for entry in tag_map:
            if 'required' in tag_map[entry]:
                found = False
                for tag in self.tags:
                    if entry == tag.name:
                        found = True
                if not found:
                    required = True
                    if self.kabi and 'required_on_kabi' in tag_map[entry]:
                        if not tag_map[entry]['required_on_kabi']:
                            required = False
                    if self.updating and 'required_on_update' in tag_map[entry]:
                        if not tag_map[entry]['required_on_update']:
                            required = False
                    if required:
                        self.errors.append(MissingTagError(None,
                                                           { 'name' : entry }))

        if self.errors:
            raise HeaderException(self.errors)

Checker = HeaderChecker
