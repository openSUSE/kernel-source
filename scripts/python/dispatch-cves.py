#!/usr/bin/python3
import os, sys, re
import bugzilla
from bugzilla._cli import DEFAULT_BZ

BSC_PATTERN = re.compile(r' bsc#([0-9][0-9]*) ')
MAINTAINERS_PATTERN = re.compile(r'\s(\S+\@suse.\S+)\s')
CLOSING_COMMENT = 'Switching back to the security team.'
SECURITY_EMAIL = 'security-team@suse.de'
MONKEY_EMAIL = 'cve-kpm@suse.de'

def check_being_logged_in(bzapi):
    if not bzapi.logged_in:
        print("You are not logged in the bugzilla!\n\nGo to https://bugzilla.suse.com/, log in via web interace with your credentials.\n"\
              "Then go to Preferences, click on the tab API KEYS and generate a new api key\nif you don't have one already.  Then store "\
              "the api_key in a file ~/.bugzillarc\nin the following format...\n\n# ~/.bugzillarc\n[apibugzilla.suse.com]\napi_key = YOUR_API_KEY")
        sys.exit(1)

def make_url(id):
    return f'https://bugzilla.suse.com/show_bug.cgi?id={id}'

class BugUpdate:
    def __init__(self, bug, comment_lines, to_append, email, action):
        self.comment = "".join(comment_lines) + to_append
        self.email = email
        self.original_email = '<unknown>'
        self.bug = bug
        self.action = action
        self.already_dispatched = False
        self.unknown_state = False
        self.cve = ''

    def __str__(self):
        return f"{make_url(self.bug)} {self.cve:<14} {self.action:<9} ({self.original_email} -> {self.email})"

    def dispatch_to_bugzilla(self, bzapi):
        if self.already_dispatched or self.unknown_state:
            return
        vals = bzapi.build_update(comment=self.comment, comment_private=True, assigned_to=self.email)
        try:
            bzapi.update_bugs([self.bug], vals)
        except Exception as e:
            print(f"Failed to update bsc#{self.bug}: {e}", file=sys.stderr)
        print(self)

def ask_user(bzapi, todo):
    print("\n*** ACTIONS ***")
    something_to_do = False
    for b in todo:
        if b.already_dispatched:
            print(f"{make_url(b.bug)} {b.cve:<14} is already dispatched to {b.email}, nothing to do!", file=sys.stderr)
            continue
        if b.unknown_state:
            print(f"{make_url(b.bug)} {b.cve:<14} is in an uknown state, better do nothing!", file=sys.stderr)
            continue
        something_to_do = True
        print(b)
    while something_to_do:
        answer = input("Do you want to submit the following updates to the bugzilla? (y/n) ")
        if answer == 'n':
            print("...aborting...", file=sys.stderr)
            return
        if answer == 'y':
            break
    print()
    for b in todo:
        b.dispatch_to_bugzilla(bzapi)

def make_unique(alist):
    try:
        return { c for c in alist if c.startswith('CVE-') }.pop()
    except:
        return ''

def update_bug_metadata(bzapi, todo):
    bugs = None
    try:
        bugs = bzapi.getbugs([ b.bug for b in todo ], include_fields=["id", "assigned_to", "alias"])
    except Exception as e:
        print(f"Couldn't query bugzilla: {e}", file=sys.stderr)
        sys.exit(4)
    if not bugs:
        print(f"Couldn't find any of the following bugs: {ids}", file=sys.stderr)
        sys.exit(5)
    emails = { b.id: b.assigned_to for b in bugs }
    cves = { b.id: make_unique(b.alias) for b in bugs }
    for b in todo:
        b.cve = cves.get(b.bug, '')
        b.original_email = emails.get(b.bug, '<unknown>')
        if b.original_email == '<unknown>':
            b.unknown_state = True
        elif b.email == b.original_email:
            b.already_dispatched = True

def handle_file(bzapi, path):
    to_dispatch = []
    with open(path, 'r') as f:
        bug = 0
        comment_lines = []
        candidates = None
        for l in f:
            comment_lines.append(l)
            m = re.search(BSC_PATTERN, l)
            if m:
                bug = int(m.group(1))
            if l.startswith('Experts candidates:'):
                mm = re.findall(MAINTAINERS_PATTERN, l)
                if mm:
                    candidates = mm
                else:
                    print("no viable maintainers: {}".format(l))
                    sys.exit(1)
        for n, c in enumerate(candidates, 1):
            print("\t{:>3}: {}".format(n, c))
        email = None
        while True:
            answer = input('(select a number, type q for abort or enter a custom email)> ')
            if answer == 'q':
                print("...aborting...", file=sys.stderr)
                sys.exit(0)
            if "@suse." in answer and ' ' not in answer:
                email = answer
            else:
                try:
                    answer = int(answer)
                    if answer < 1 or answer > len(candidates):
                        raise Exception()
                except:
                    print("{} is not a number between 1 and {}.".format(answer, len(candidates)))
                    continue
                email = candidates[answer - 1]
            break
        to_add = []
        while True:
            append = input('Anything to add to the c-k-f comment? (type q for abort and empty line for finish)> ')
            if append == 'q':
                print("...aborting...", file=sys.stderr)
                sys.exit(0)
            if not append:
                break
            to_add.append(append)
        if to_add:
            to_add = '\n\n' + "\n".join(to_add)
        else:
            to_add = ''
        to_dispatch.append(BugUpdate(bug, comment_lines, to_add, email, 'developer'))
    update_bug_metadata(bzapi, to_dispatch)
    ask_user(bzapi, to_dispatch)

def handle_dir(bzapi, path):
    to_dispatch = []
    for subdir, dirs, files in os.walk(path):
        for ckf in files:
            dirpath = subdir + os.sep + ckf
            with open(dirpath, 'r') as f:
                bug = 0
                is_invalid = False
                is_already_fixed = False
                comment_lines = []
                for l in f:
                    comment_lines.append(l)
                    m = re.search(BSC_PATTERN, l)
                    if m:
                        bug = int(m.group(1))
                    if l.startswith('No codestream affected'):
                        is_invalid = True
                    elif l.startswith('NO ACTION NEEDED'):
                        is_already_fixed = True
                if not bug:
                    continue
                if is_invalid:
                    to_dispatch.append(BugUpdate(bug, comment_lines, "\n\nNot relevant for us.  " + CLOSING_COMMENT, SECURITY_EMAIL, 'invalid'))
                elif is_already_fixed:
                    to_dispatch.append(BugUpdate(bug, comment_lines, "\n\nAlready fixed on all branches.  " + CLOSING_COMMENT, SECURITY_EMAIL, 'fixed'))
                else:
                    to_dispatch.append(BugUpdate(bug, comment_lines, "\n\nSeems trivial enough -> patch monkey queue.", MONKEY_EMAIL, 'monkey'))
    update_bug_metadata(bzapi, to_dispatch)
    ask_user(bzapi, to_dispatch)

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("The scripts expects exactly 1 argument that is either a regular file or a directory.")
        sys.exit(3)

    bzapi = bugzilla.Bugzilla(DEFAULT_BZ)
    check_being_logged_in(bzapi)

    path=sys.argv[1]

    if os.path.isfile(path):
        handle_file(bzapi, path)
        sys.exit(0)

    if os.path.isdir(path):
        handle_dir(bzapi, path)
        sys.exit(0)

    print("{} must be either regular file or a directory".format(path), file=sys.stderr)
    sys.exit(1)
