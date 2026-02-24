import bugzilla, os, re, sys
from bugzilla._cli import DEFAULT_BZ

CVSS_PATTERN = re.compile(r"CVSSv3.1:SUSE:CVE-[0-9]{4}-[0-9]{4,}:([0-9].[0-9])")
TIME_FORMAT_XML = '%Y%m%dT%H:%M:%S'
TIME_FORMAT_REST = '%Y-%m-%dT%H:%M:%SZ'

def handle_email(email):
    if email == '__empty-env-var__':
        print("Please set the environment variable BUGZILLA_ACCOUNT_EMAIL to your bugzilla email or provide it after --email (-e).", file=sys.stderr)
        sys.exit(1)
    return email

def get_score(s):
    m = re.search(CVSS_PATTERN, s)
    return m.group(1) if m else ''

def get_bugzilla_api(rest=False):
    bzapi = bugzilla.Bugzilla(url=None, force_rest=rest)
    configpath = os.getenv('HOME') + os.sep + '.bugzillarc'
    user_email = os.environ.get('BUGZILLA_ACCOUNT_EMAIL', None)
    if user_email and '@' in user_email:
        name = user_email.split('@')[0]
        new_configpath = f'{configpath}.{name}'
        if os.path.exists(new_configpath):
            configpath = new_configpath
    if os.path.exists(configpath):
        bzapi.readconfig(configpath=configpath, overwrite=True)
    bzapi.connect(DEFAULT_BZ)
    return bzapi

def check_being_logged_in(bzapi):
    if not bzapi.logged_in:
        print("You are not logged in the bugzilla!\n\nGo to https://bugzilla.suse.com/, log in via web interface with your credentials.\n"\
             "Then go to Preferences, click on the tab API KEYS and generate a new api key\nif you don't have one already.  Then store "\
             "the api_key in a file ~/.bugzillarc\nin the following format...\n\n# ~/.bugzillarc\n[apibugzilla.suse.com]\napi_key = YOUR_API_KEY",
             file=sys.stderr)
        return False
    return True

def make_unique(alist):
    try:
        return { c for c in alist if c.startswith('CVE-') }.pop()
    except:
        return ''

def make_url(bug_id):
    return f'https://bugzilla.suse.com/show_bug.cgi?id={bug_id}'

def get_exportpatch_string(references, h, patch_dir):
    return f'exportpatch -w -s -d {patch_dir} {" ".join(f"-F {r}" for r in references)} {h}'

def get_insert_string(rel_path, name):
    return f'{rel_path}/scripts/git_sort/series_insert {name}'

def create_cache_dir(program_dir):
    cache_dir = os.getenv('XDG_CACHE_HOME', None)
    if not cache_dir:
        cache_dir = os.getenv('HOME', None)
        if not cache_dir:
            sys.exit(2)
        cache_dir = cache_dir + os.sep + '.cache'
    if not os.path.isdir(cache_dir):
        os.mkdir(cache_dir)
    if not os.path.isdir(cache_dir):
        sys.exit(3)
    program_dir = cache_dir + os.sep + program_dir
    if not os.path.isdir(program_dir):
        os.mkdir(program_dir)
    if not os.path.isdir(program_dir):
        sys.exit(4)
    return program_dir
