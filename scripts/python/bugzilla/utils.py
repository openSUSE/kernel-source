import bugzilla, datetime, os
from bugzilla._cli import DEFAULT_BZ

def get_bugzilla_api():
    return bugzilla.Bugzilla(DEFAULT_BZ)

def check_being_logged_in(bzapi):
    if not bzapi.logged_in:
        print("You are not logged in the bugzilla!\n\nGo to https://bugzilla.suse.com/, log in via web interace with your credentials.\n"\
             "Then go to Preferences, click on the tab API KEYS and generate a new api key\nif you don't have one already.  Then store "\
             "the api_key in a file ~/.bugzillarc\nin the following format...\n\n# ~/.bugzillarc\n[apibugzilla.suse.com]\napi_key = YOUR_API_KEY")
        return False
    return True

def make_unique(alist):
    try:
        return { c for c in alist if c.startswith('CVE-') }.pop()
    except:
        return ''

def make_url(bug_id):
    return f'https://bugzilla.suse.com/show_bug.cgi?id={bug_id}'

def format_time(t):
    return datetime.datetime.strptime(str(t), '%Y%m%dT%H:%M:%S')

def get_backport_string(references, h, comment):
    return f'./scripts/git_sort/series_insert.py patches.suse/$(exportpatch -w -s -d patches.suse {" ".join(f"-F {r}" for r in references)} {h}) # {comment}'

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
