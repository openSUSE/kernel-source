import os
import re
import sys
import argparse
import subprocess
import textwrap
from bugzilla.utils import make_url, make_unique, calculate_deadline, format_time

# dispatch-cves script - is based on python-bugzilla (our in-tree patched copy) and requests libraries
# for now this script should be kept Python 3.6 compatible (SLE15-SP7)

BSC_PATTERN = re.compile(r'\sbsc#([0-9][0-9]*)\s')
CVSS_PATTERN = re.compile(r'\swith\s+CVSS\s*([0-9]?[0-9](\.[0-9]*)?)\s')
MAINTAINERS_PATTERN = re.compile(r'\s(\S+\@suse.\S+\s\([0-9]+\))')
EMAIL_PATTERN = re.compile(r'[\s,:](\S+@\S*suse\.[^\s,:]+)')
CC_PATTERN = re.compile(r'^\s*CC[\s:]\s*\S')
NEEDINFO_PATTERN = re.compile(r'^\s*NEEDINFO[\s:]\s*\S')
ASSIGNEE_PATTERN = re.compile(r'^\s*ASSIGNEE[\s:]\s*\S')
BLACKLIST_PATTERN = re.compile(r'^\s*BLACKLIST[\s:]\s*(\S.*?)\s*$')
ACTION_PATTERN = re.compile(r'^(\S+):\s+MANUAL:\s')
BLACKLIST_ALL = '*'
SECURITY_EMAIL = 'kernel-security-sentinel@lists.suse.com'
MONKEY_EMAIL = 'cve-kpm@suse.de'
QUEUE_EMAIL = 'kernel-bugs@suse.de'
SECURITY_PRODUCT = 'SUSE Security Incidents'
COMMENT_BANLIST = [ 'swamp@suse.de', 'bwiedemann+obsbugzillabot@suse.com', 'maint-coord+maintenance-robot@suse.de', 'smash_bz@suse.de' ]
MIN_COMMENTS = 2
# ../../cve_tools/blacklist-cve
BLACKLIST_CVE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                             'cve_tools', 'blacklist-cve')

def parse_blacklist(spec):
    branches = spec.split(maxsplit=1)[0].split(',')
    if BLACKLIST_ALL not in branches:
        return branches
    # the wildcard already covers everything, mixing is most likely a typo
    return BLACKLIST_ALL if len(branches) == 1 else None

class BugUpdate:
    def __init__(self, path_to_remove, bug, cvss, comment_lines, to_append, email, action, cc_list=None, needinfo_list=None,
                 blacklist_branches=[]):
        self.path_to_remove = path_to_remove
        self.comment = "".join(comment_lines) + to_append
        self.email = email
        self.original_email = '<unknown>'
        self.bug = bug
        self.in_cvss = cvss
        self.action = action
        self.already_dispatched = False
        self.unknown_state = False
        self.self_assign = False
        self.product = ''
        self.cc_list = cc_list if cc_list else []
        self.needinfo_list = needinfo_list if needinfo_list else []
        self.blacklist_branches = blacklist_branches
        self.cc_add = []
        self.cve = ''
        self.deadline = None
        self.any_flags = False
        self.bz_comments = []
        self.human_comments = []

    def __str__(self):
        return "{} {:<14} {:<9} ({} -> {}{}{}{}{})".format(
                make_url(self.bug),
                self.cve,
                self.action,
                self.original_email, self.email,
                ', CC: ' + ', '.join(self.cc_add) if self.cc_add else '',
                ', NEEDINFO: ' + ', '.join(self.needinfo_list) if self.needinfo_list else '',
                ', DEADLINE: ' + str(self.deadline) if self.deadline else '',
                ', BLACKLIST: ' + ','.join(self.blacklist_branches) if self.blacklist_branches else '',
                )

    # The comment we are about to add is appended at the end, so it gets the
    # number of the already existing ones.
    def comment_ref(self):
        return '{}#c{}'.format(make_url(self.bug), len(self.bz_comments))

    def blacklist_cmd(self):
        cmd = [ BLACKLIST_CVE, 'add', self.cve, ','.join(self.blacklist_branches), self.comment_ref() ]
        return cmd

    def request_blacklist(self):
        if not self.blacklist_branches:
            return False
        cmd = self.blacklist_cmd()
        print('Running: {}'.format(' '.join(cmd)))
        try:
            subprocess.run(cmd, check=True)
        except Exception as e:
            print(f"Failed to request blacklisting of {self.cve} referencing {self.comment_ref()}: {e}", file=sys.stderr)
            return False
        return True

    # Keep the checks in sync with the ones ask_user() reports about, otherwise
    # a bug announced as 'nothing to do' would be updated anyway.
    def dispatch_to_bugzilla(self, bzapi, force, allow_same_assignee):
        if self.product != SECURITY_PRODUCT and not force:
            return
        if self.self_assign and not force and not allow_same_assignee:
            return
        if self.unknown_state and not force:
            return
        if self.already_dispatched and not force:
            return
        bargs = { 'comment': self.comment, 'comment_private': True, 'assigned_to': self.email }
        if self.cc_add:
            bargs['cc_add'] = self.cc_add
        if self.needinfo_list and not self.any_flags:
            bargs['flags'] = [ { 'name': 'needinfo', 'requestee': rmail, 'status': '?', 'type_id': 4 } for rmail in self.needinfo_list ]
        if self.deadline is not None:
            bargs['deadline'] = self.deadline.strftime('%Y-%m-%d')

        vals = bzapi.build_update(**bargs)
        if self.any_flags:
            print(f'Warning: bsc#{self.bug} has already flags set, skipping needinfo update!', file=sys.stderr)
        try:
            bzapi.update_bugs([self.bug], vals)
        except Exception as e:
            print(f"Failed to update bsc#{self.bug}: {e}", file=sys.stderr)
            return
        print(f'OK: {self.comment_ref()}')
        # The blacklist request refers to the comment added above, hence it can
        # only be submitted once the bugzilla update went through.
        if self.blacklist_branches and not self.request_blacklist():
            return
        if self.path_to_remove:
            os.remove(self.path_to_remove)

def ask_user(bzapi, todo, yes, force, allow_same_assignee):
    print("\n*** ACTIONS ***")
    something_to_do = False
    for b in todo:
        if not force and b.product != SECURITY_PRODUCT:
            print(f"{make_url(b.bug)} {b.cve:<14} belongs to unsupported product {b.product}, expected {SECURITY_PRODUCT}, nothing to do!", file=sys.stderr)
            continue
        if not force and not allow_same_assignee and b.self_assign:
            print(f"{make_url(b.bug)} {b.cve:<14} is already assigned to {b.email}, nothing to do!", file=sys.stderr)
            continue
        if not force and b.unknown_state:
            print(f"{make_url(b.bug)} {b.cve:<14} is in an uknown state, better do nothing!", file=sys.stderr)
            continue
        if not force and b.already_dispatched:
            print(f"{make_url(b.bug)} {b.cve:<14} is already dispatched to {b.original_email}, better do nothing!", file=sys.stderr)
            if b.original_email != b.email:
                print(f"WARNING: you want to dispatch to {b.email}, but the bug is dispatched to {b.original_email} already!", file=sys.stderr)
            continue
        if len(b.human_comments) > MIN_COMMENTS:
            print(f"WARNING: {make_url(b.bug)} might not be a new bug.  Have a look at the history.  "\
                  f"The last human comment (#{len(b.human_comments)}) is in {make_url(b.bug)}#c{b.human_comments[len(b.human_comments) - 1]['count']}!", file=sys.stderr)
        something_to_do = True
        print(b)
    if not yes:
        while something_to_do:
            answer = input("Do you want to submit the following updates to the bugzilla? (y/n) ")
            if answer == 'n':
                print("...aborting...", file=sys.stderr)
                return
            if answer == 'y':
                break
    print()
    for b in todo:
        b.dispatch_to_bugzilla(bzapi, force, allow_same_assignee)

def update_bug_metadata(bzapi, todo):
    bugs, comments = None, None
    try:
        bugs = bzapi.getbugs([ b.bug for b in todo ], include_fields=[
            "id", "assigned_to", "alias", "cc", "flags", "product", "deadline", "creation_time"])
        comments = bzapi.get_comments([ b.bug for b in todo ])
    except Exception as e:
        print(f"Couldn't query bugzilla: {e}", file=sys.stderr)
        sys.exit(4)
    if not bugs:
        print(f"Couldn't find any of the following bugs: {[ b.bug for b in todo ]}", file=sys.stderr)
        sys.exit(5)
    bugmap = { b.id: b for b in bugs }

    for b in todo:
        b.bz_comments = comments['bugs'][str(b.bug)]['comments']
        b.human_comments = [ c for c in b.bz_comments if c['creator'] not in COMMENT_BANLIST ]
        b.cve = make_unique(bugmap[b.bug].alias)        if b.bug in bugmap else ''
        b.original_email = bugmap[b.bug].assigned_to    if b.bug in bugmap else '<unknown>'
        b.any_flags = bool(bugmap[b.bug].flags)         if b.bug in bugmap else False
        b.product = bugmap[b.bug].product               if b.bug in bugmap else ''
        b.deadline = calculate_deadline(format_time(bugmap[b.bug].creation_time), b.in_cvss) \
                                                        if b.bug in bugmap else None

        if b.bug in bugmap:
            b.cc_add = list(set(b.cc_list) - set(bugmap[b.bug].cc))
        if b.original_email == '<unknown>':
            b.unknown_state = True
        elif b.original_email == b.email:
            b.self_assign = True
        elif QUEUE_EMAIL != 'ANY' and b.original_email != QUEUE_EMAIL:
            b.already_dispatched = True

def handle_file(bzapi, path, to_dispatch, remove_file, is_interactive=True, cc_us=None):
    with open(path, 'r') as f:
        decided = False
        bug = 0
        cvss = None
        comment_lines = []
        candidates = []
        candidate_emails = []
        cc_list = []
        if cc_us:
            cc_list.append(cc_us)
        needinfo_list = []
        blacklist_branches = []
        action_branches = []
        for l in f:
            should_go_out = True
            blacklist_m = re.match(BLACKLIST_PATTERN, l)
            action_m = re.match(ACTION_PATTERN, l)
            if action_m:
                action_branches.append(action_m.group(1))
            if l.startswith('Security fix for CVE-'):
                m = re.search(BSC_PATTERN, l)
                if m:
                    bug = int(m.group(1))
                m = re.search(CVSS_PATTERN, l)
                if m:
                    cvss = m.group(1)
            if l.startswith('NO CODESTREAM AFFECTED') or l.startswith('NO ACTION NEEDED'):
                candidate_emails = [ SECURITY_EMAIL ]
                decided = True
            elif 'TRIVIAL_BACKPORT' in l:
                candidate_emails = [ MONKEY_EMAIL ]
                decided = True
                should_go_out = False
            elif re.search(ASSIGNEE_PATTERN, l):
                mm = re.findall(EMAIL_PATTERN, l)
                if mm and len(mm) == 1:
                    candidate_emails = mm
                    decided = True
                should_go_out = False
            elif re.search(CC_PATTERN, l):
                mm = re.findall(EMAIL_PATTERN, l)
                if mm:
                   cc_list.extend(mm)
                should_go_out = False
            elif re.search(NEEDINFO_PATTERN, l):
                mm = re.findall(EMAIL_PATTERN, l)
                if mm:
                   needinfo_list.extend(mm)
                should_go_out = False
            elif blacklist_m:
                blacklist_branches = parse_blacklist(blacklist_m.group(1))
                if not blacklist_branches:
                    print(f"'{path}' has a malformed BLACKLIST stanza ('{blacklist_m.group(1)}'), "\
                          f"expected '<branch1>,<branch2>,... ' or '{BLACKLIST_ALL}', skipping.", file=sys.stderr)
                    return
                should_go_out = False
            elif l.startswith('Experts candidates:'):
                mm = re.findall(MAINTAINERS_PATTERN, l)
                if mm:
                    candidates = mm
                should_go_out = False
                if is_interactive:
                    print(l)
            elif l.startswith('COMMENT:'):
                should_go_out = False
            if should_go_out:
                comment_lines.append(l)
        if not bug:
            print(f"'{path}' doesn't seem to contain any bug number, skipping.  Be sure to regenerate c-k-f output with all the repos up-to-date.", file=sys.stderr)
            return
        if blacklist_branches is BLACKLIST_ALL:
            blacklist_branches = action_branches
        # Blacklisting all the branches that need an action is a final verdict,
        # so the bug goes back to the security team unless an explicit ASSIGNEE
        if not decided and blacklist_branches:
            undecided_b = [ b for b in action_branches if b not in blacklist_branches ]
            if undecided_b:
                print(f"'{path}' (bsc#{bug}) is not decided by the blacklisting, "\
                      f"{','.join(undecided_b)} still needs an action.", file=sys.stderr)
            else:
                candidate_emails = [ SECURITY_EMAIL ]
                decided = True
        if not decided and candidates:
            candidates.append(MONKEY_EMAIL)
            candidate_emails = [ e.split(" ")[0] for e in candidates ]

        if not candidate_emails:
            print(f"{path} doesn't have any viable assignees.", file=sys.stderr)
            if is_interactive:
                sys.exit(1)
            else:
                return

        if is_interactive:
            for cl in comment_lines:
                print(cl, end='')
        email = None if len(candidate_emails) != 1 else candidate_emails[0]
        if not email:
            if not is_interactive:
                print(f'Skipping {path} (bsc#{bug}) due to missing ASSIGNEE!', file=sys.stderr)
                return
            for n, c in enumerate(candidates, 1):
                print("\t{:>3}: {}".format(n, c))
        while not email:
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
                email = candidate_emails[answer - 1]
            break
        to_add = ''
        if blacklist_branches:
            to_add = '\nRequesting to blacklist the CVE for: {}\n'.format(','.join(blacklist_branches))
        to_dispatch.append(BugUpdate(path if remove_file else None, bug, cvss, comment_lines, to_add, email, 'developer', cc_list, needinfo_list, blacklist_branches))

def single_dispatch(bzapi, path, remove_file, yes, force, cc_us, allow_same_assignee):
    to_dispatch = []
    handle_file(bzapi, path, to_dispatch, remove_file, is_interactive=not yes, cc_us=cc_us)
    update_bug_metadata(bzapi, to_dispatch)
    ask_user(bzapi, to_dispatch, yes, force, allow_same_assignee)

def multiple_dispatch(bzapi, path, remove_file, yes, force, cc_us, allow_same_assignee):
    to_dispatch = []
    nfiles = 0
    for subdir, dirs, files in os.walk(path):
        for ckf in files:
            nfiles += 1
            opath = subdir + os.sep + ckf
            handle_file(bzapi, opath, to_dispatch, remove_file, is_interactive=False, cc_us=cc_us)
    if not nfiles:
        sys.exit(0)
    update_bug_metadata(bzapi, to_dispatch)
    ask_user(bzapi, to_dispatch, yes, force, allow_same_assignee)

def parse_args():
    global SECURITY_EMAIL, QUEUE_EMAIL
    parser = argparse.ArgumentParser(formatter_class=argparse.RawDescriptionHelpFormatter,
                                     description=textwrap.dedent('''Updating bugzilla based on ./scripts/check-kernel-fix output. There are 2 modes.

1/ File mode (single dispatch) where the input is a single file containing ./scripts/check-kernel-fix output.
You can append the following to the c-k-f output and will be interpreted by this script.

ASSIGNEE <email1>
CC <email1> <email2> ...
NEEDINFO <email1> <email2> ...
TRIVIAL_BACKPORT
BLACKLIST <branch1>,<branch2>,...
BLACKLIST *

2/ Directory mode (multiple dispatch) is like File mode, but it goes through all the files in a directory
and processes only those that do not need an input, skipping the rest.

The bugzilla comment will always contain copy of the ./scripts/check-kernel-fix output taken from the file.
BLACKLIST takes the same branch list as ./scripts/cve_tools/blacklist-cve, '*' is a shortcut
for all the branches that the c-k-f output reports as needing an action ('<branch>: MANUAL: ...').
The request is submitted only after the bugzilla comment it refers to has been added.  When the
blacklisted branches cover all the branches that need an action, the CVE is considered decided
and the bug is handed over to the security team (unless an explicit ASSIGNEE says otherwise),
a partial blacklisting is dispatched like any other bug.
    '''))
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("-f", "--file", help="path to a regular file containing ./scripts/check-kernel-fix output", default=None, type=str)
    group.add_argument("-d", "--dir", help="path to directory containing regular files with ./scripts/check-kernel-fix outputs", default=None, type=str)

    parser.add_argument("-r", "--remove-file", help="Remove file after dispatching CVE", default=None, action="store_true")
    parser.add_argument("-y", "--yes", help="Dispatch without asking; never use :-)", default=None, action="store_true")
    parser.add_argument("--force", help="Bypass all dispatch checks (unknown state, already dispatched, self-assignment)", default=None, action="store_true")
    parser.add_argument("--allow-same-assignee",
                        help="Proceed even when the bug is already assigned to the target assignee "
                             "(re-posts the comment and updates CC/needinfo without changing the assignee).",
                        default=False, action="store_true")
    parser.add_argument("--no-cc-self", help="Do not CC yourself", default=None, action="store_true")
    parser.add_argument("--rest", help="Use REST API instead of XMLRPC APII (experimental, for debugging purposes)", action="store_true", default=False)
    parser.add_argument("--override-noaction-assignee",
                        help="Assignee for 'NO ACTION NEEDED' / 'NO CODESTREAM AFFECTED' cases. "
                             f"(Overrides default SECURITY_EMAIL={SECURITY_EMAIL})",
                        default=None)
    parser.add_argument("--override-source-assignee",
                        help="The email to treat as the 'queue' or starting point for dispatch, "
                             "or the special value 'ANY' to dispatch regardless of the current assignee. "
                             f"(Overrides default QUEUE_EMAIL={QUEUE_EMAIL})",
                        default=None)

    args = parser.parse_args()

    if args.override_noaction_assignee:
        SECURITY_EMAIL = args.override_noaction_assignee

    if args.override_source_assignee:
        QUEUE_EMAIL = args.override_source_assignee

    return args
