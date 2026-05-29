#! /usr/bin/env python3
"""
Synopsis: determine the current kernel source version from a series of patches
          as being defined in series.conf

Usage: {appname} [-hVvb:p:]
       -h, --help           this message
       -V, --version        print version and exit
       -v, --verbose        verbose mode (cumulative)
       -b, --basedir dir    base directory, holding rpm/config.sh, series.conf,
                            default: '{basedir}'
       -p, --patches dir    directory, where patches.* reside, referenced in
                            series.conf, default: '{patches}'

Description:
The executable part of this script replaces the old compute-PATCHVERSION.sh
script. It is expected to be executed in the kernel-source base folder, e.g.:

        ./rpm/compute-PATCHVERSION.py

This file is typically a symlink to ../scripts/python/kutil/config.py.

It fetches the kernel source version from ./rpm/config.sh, then parses the
./series.conf file, collecting all patch files, and tracks for any changes in
top level Makefiles to the four version defining symbols: VERSION, PATCHLEVEL,
SUBLEVEL, and EXTRAVERSION. The result should consitute the latest kernel
patch level.

Version: {version}
Copyright: (c)2026 by {company}
Author: {author}
License: {license}
"""
#
# vim:set et ts=8 sw=4:
#

import configparser
import subprocess
import os

# some commonly used functions

def uniq(lst):
    # fairly slow but does not require any special property of elements nor ordered dictionaries
    return [x for i, x in enumerate(lst) if i == lst.index(x)]

def init_repo(tmpdirname, repo, branch):
    subprocess.check_call(['git', 'init', '-q', '--object-format=sha256', '-b', branch, repo], cwd=tmpdirname)
    return os.path.join(tmpdirname, repo)

def get_source_timestamp(directory):
    with open(os.path.join(directory, 'source-timestamp'), 'r') as fd:
        source_timestamp = fd.read().splitlines()
    return '\n'.join(source_timestamp[1:] + [source_timestamp[0]])

def list_files(directory):
    if len(directory) > 1:
        directory = directory.rstrip('/')
    result = []
    for root, dirs, filenames in os.walk(directory):
        for f in filenames:
            result.append(os.path.join(root, f)[len(directory)+1:])
    return sorted(result)

def list_specs(directory):
    ext = '.spec'
    return [f[0:-len(ext)] for f in list_files(directory) if f.endswith(ext)]

def _unquote(val):
    # From kbuild2.conf parser.
    ret = ''
    inquotes = False
    idx = 0
    while idx < len(val):
        endidx = idx
        escaped = False
        while endidx < len(val):
            if escaped:
                escaped = False
            elif val[endidx] in '$"\'':
                break
            elif not inquotes and val[endidx] == '\\':
                escaped = True
            endidx += 1
        ret += val[idx:endidx]
        idx = endidx
        if idx >= len(val):
            break
        if val[idx] == '"':
            inquotes = not inquotes
            idx += 1
        elif not inquotes and val[idx] == "'":
            endidx = val.index("'", idx + 1)
            ret += val[idx+1:endidx]
            idx = endidx + 1
    return ret

def read_source_timestamp(directory):
    file = os.path.join(directory, 'source-timestamp')
    cp = configparser.ConfigParser(delimiters=(':'), interpolation=None)
    with open(file, 'r') as fd:
        cp.read_string('[section]\nDate: ' + fd.read())
    config = cp['section']
    return config

def read_config_sh(package_tar_up_dir):
    file = os.path.join(package_tar_up_dir, 'config.sh')
    cp = configparser.ConfigParser(delimiters=('='), interpolation=None)
    with open(file, 'r') as fd:
        cp.read_string('[section]\n' + fd.read())

    config = cp['section']

    options = cp.options('section')

    for o in options:
        val = config.get(o)
        unq = _unquote(val)
        if unq != val:
            cp.set('section', o, unq)

    return config

def get_kernel_project_package(package_tar_up_dir):
    rpm_config = read_config_sh(package_tar_up_dir)
    if 'ibs_project' in rpm_config:
        project = rpm_config.get('ibs_project')
    else:
        project = rpm_config.get('obs_project')
    if 'variant' in rpm_config:
        return (project, 'kernel-source' + rpm_config.get('variant'))
    # kgraft patches have only one spec file, use file list
    lst = list_specs(package_tar_up_dir)
    assert len(lst) == 1
    specname = lst[0]
    assert '/' not in specname
    return (project, specname)

def get_kernel_projects(package_tar_up_dir):
    rpm_config = read_config_sh(package_tar_up_dir)
    ibs_projects = {}
    obs_projects = {}
    for var in sorted(list(rpm_config.keys())):
        suffix = var[len('ibs_project_'):].upper()
        if var.startswith('ibs_project'):
            ibs_projects[suffix] = rpm_config[var]
        if var.startswith('obs_project'):
            obs_projects[suffix] = rpm_config[var]
            if suffix not in ibs_projects:  # sorted so that IBS comes first
                ibs_projects[suffix] = 'openSUSE.org:' + rpm_config[var]
    return {'IBS': ibs_projects, 'OBS': obs_projects}

# While the sources do contain config.conf the tar-up can produce sources
# for fewer architectures than specified in config.conf when using -a
# option (ie. disable some architectures)
# The architectures to build for have to be read from the spec file
# ExclusiveArch tags as a result. While not every spec file may have one
# for all binary packages the tag is generated based on the list of
# architectures for which the config is enabled.
# In general the tag coulld be wrapped as e-mail headers can but we only
# need to support spec files generated from kernel spec file templates in
# which the list of architectures is always on one line.
# Multiple ExclusiveArgs tags may exist because of repository conditionals.
# Dummy architectures like do_not_build or noarch are not provided by
# repositories and do not affect the repository selection.
def get_package_archs(package_tar_up_dir, limit_packages=None):
    ext = '.spec'
    tag = 'ExclusiveArch:'.lower()
    limit_packages = limit_packages if limit_packages else []
    limit_packages = [ spec if spec.endswith(ext) else spec + ext for spec in limit_packages ]
    limit_packages = limit_packages + [ 'kernel-' + spec for spec in limit_packages ] # limit-packages fuzzing, this may need to go to caller
    lst = list_files(package_tar_up_dir)
    lst = [f for f in lst if f.endswith(ext)]
    archs = []
    for spec in lst:
        if limit_packages and spec not in limit_packages:
            continue
        with open(os.path.join(package_tar_up_dir, spec), 'r') as f:
            for l in f.read().splitlines():
                if l.lower().startswith(tag):
                    l = l[len(tag):]
                    # limit expansion to what can realistically be expected in OBS project configuration
                    # local rpm may have different ideas or be completely unavailable, use fixed expansion
                    l = l.replace('%ix86', 'i386 i486 i586 i686')
                    l = l.replace('%arm', 'armv6l armv6hl armv7l armv7hl')
                    l = l.replace('\t', ' ').strip()
                    assert '%' not in l  # will need to do more macro expansion otherwise
                    archs += l.split(' ')
    return sorted(list(set(archs)))

# here starts the new compute-PATCHVERSION.py implementation

if __name__ == "__main__":
    import os
    import re
    import sys
    import shlex
    import getopt
    import signal

    __version__ = '0.1'
    __company__ = 'SUSE LLC'
    __author__ = 'Hans-Peter Jansen <hp.jansen@suse.com>'
    __license__ = 'GNU GPL v2 - see http://www.gnu.org/licenses/gpl2.txt for details'

    class gpar:
        """Global parameter class"""
        appdir, appname = os.path.split(sys.argv[0])
        if appdir == '.':
            appdir = os.getcwd()
        if appname.endswith('.py'):
            appname = appname[:-3]
        pid = os.getpid()
        version = __version__
        company = __company__
        author = __author__
        license = __license__
        loglevel = 0
        basedir = '.'
        patches = '.'


    stdout = lambda *msg: print(*msg, file = sys.stdout, flush = True)
    stderr = lambda *msg: print(*msg, file = sys.stderr, flush = True)


    def vout(lvl, *msg):
        """Verbose output"""
        if lvl <= gpar.loglevel:
            stderr(*msg)


    def exit(ret = 0, msg = None, usage = False):
        """Terminate process with optional message and usage"""
        if msg:
            stderr('{}: {}'.format(gpar.appname, msg))
        if usage:
            stderr(__doc__.format(**gpar.__dict__))
        sys.exit(ret)


    def parse_config_sh(config_sh):
        """Parse config.sh file and return a dict with key value pairs"""
        config = {}
        lnnr = 0
        with open(config_sh, 'r') as f:
            for line in f:
                lnnr += 1
                line = line.strip()
                if not line or line.startswith('#'):
                    continue

                if '=' in line:
                    key, raw_value = line.split('=', 1)
                    key = key.strip()
                    # shlex removes the outer quotation marks cleanly
                    parsed_tokens = shlex.split(raw_value)
                    value = parsed_tokens[0] if parsed_tokens else ""
                    config[key] = value
                else:
                    raise ValueError('line {} malformed in {}: "{}"'.format(lnnr, config_sh, line))

        return config


    class SrcVersion:
        """Class, defining a source code version allows parsing from string, updating single values
        and returns the resulting version as string repr"""
        def __init__(self, version_str):
            self.version = '0'
            self.patchlevel = '0'
            self.sublevel = '0'
            self.extraversion = ''
            self._partlist = ('version', 'patchlevel', 'sublevel', 'extraversion')
            pattern = re.compile(r'''
                ^                           # Start of line
                (?P<version>\d+)            # Required: version number
                \.                          # Required: version dot
                (?P<patchlevel>\d+)         # Required: patchlevel number
                (?:                         # Start of non-capturing group
                    \.(?P<sublevel>\d+)     # Optional: sublevel number
                )?                          # End of group
                (?P<extraversion>.*)        # Optional: extra version
                $                           # End of line
            ''', re.VERBOSE)

            match = re.match(pattern, version_str)
            if not match:
                raise ValueError('Invalid version str: "{}". Expecting X[.Y][.Z][-extra]'.format(version_str))
            for part in self._partlist:
                value = match.group(part)
                if value is not None:
                    self.update(part, value)

        def update(self, part, value):
            """Update a specific version component to a new value"""
            if part in self._partlist:
                setattr(self, part, value)

        def __str__(self):
            return '{version}.{patchlevel}.{sublevel}{extraversion}'.format(**self.__dict__)


    def parse_series_conf(basedir, series_conf):
        """Parse the series.conf file, taking guards into account, and return a list of patch files"""
        pattern = re.compile(r'''
            ^                   # Start of line
            (?:                 # Start of non-capturing group for sign and symbol
                (?P<sign>[+-])  # Required if group matches: Matches a single '+' or '-' sign
                (?P<symbol>[a-zA-Z0-9]+)? # Optional: Matches alphanumeric symbol only after a sign
            )?                  # End of group: The entire sign+symbol block is optional
            \s*                 # Optional: Ignores any subsequent whitespace characters
            (?P<patch>\S+)      # Required: Matches the filename (one or more non-whitespace characters)
            .*?                 # Optional: Ignore any trailing garbarge
            $                   # End of line
        ''', re.VERBOSE)

        patches = []
        lnnr = 0
        with open(series_conf, 'r') as f:
            for line in f:
                lnnr += 1
                line = line.strip()
                if not line or line.startswith('#'):
                    continue

                m = re.match(pattern, line)
                if m:
                    guard = m['sign']
                    if guard:
                        # guarded line
                        if guard == '+':
                            vout(2, '{}: patch in line {} flagged: {}'.format(series_conf, lnnr, line))
                        else:
                            # guard == '-':
                            vout(2, '{}: patch in line {} excluded: {}'.format(series_conf, lnnr, line))
                    patches.append(m['patch'])
                else:
                    raise ValueError('{}: line {} malformed: "{}"'.format(series_conf, lnnr, line))

        return patches


    def parse_makefiles(diff_text):
        """Locate changes to the toplevel Makefile in a unified diff file
        return applied changesets to the linux kernel version variables"""
        # match top level Makefile
        makefile_target = re.compile(r'''
            ^                   # Anchor a start of line
            (---|\+\+\+)        # Match either +++ or ---
            \s+                 # Skip blinks
            (?P<path>[^\/]+/Makefile)   # Extract Makefile with single slash
            ( |\t|$)            # May end in a blank, tab or end of line
        ''', re.VERBOSE)
        # match variable change pattern
        var_pattern = re.compile(r'''
            ^                   # Anchor at start of line
            \+                  # Required: we care about additions ('+') only
            \s*                 # Skip optional blanks
            (?P<key>VERSION|PATCHLEVEL|SUBLEVEL|EXTRAVERSION)   # Required: key value is one of these
            \s*=\s*             # Required: assignment with optional blanks
            (?P<value>.*)       # Required: any value, even an empty one
        ''', re.VERBOSE)

        in_makefile = False
        changes = []

        for line in diff_text.splitlines():
            if line.startswith(('--- ', '+++ ')):
                match = makefile_target.match(line)
                if match:
                    # we're in a toplevel Makefile diff section now
                    in_makefile = True
                    current_file = match.group('path')
                    vout(4, 'parse_makefiles: {}'.format(current_file))
                else:
                    # we're in some other files modification context
                    in_makefile = False

            if not in_makefile:
                continue

            if line.startswith((' ', '@@')):
                continue

            # extract version variable changes
            match = var_pattern.match(line)
            if match:
                changes.append(
                    {
                        # which variable (and avoid shouting loudly)
                        'variable': match.group('key').lower(),
                        # added (new) or removed (old) value
                        'value': match.group('value').strip(),
                    }
                )

        return changes


    def compute(basedir, patchdir):
        """Compute patchversion from config.sh, series.conf and patch files"""
        ret = 0
        if not os.path.isdir(basedir):
            exit(1, 'patches basedir {} not found'.format(basedir))

        # fetch key value pairs from config.sh
        config_sh = os.path.join(basedir, 'rpm/config.sh')
        config = parse_config_sh(config_sh)
        vout(2, 'config.sh: {}'.format(config))

        # determine kernel base source code version
        src_version = SrcVersion(config['SRCVERSION'])
        vout(1, 'base source version is: {}'.format(src_version))

        # fetch patch files from series.conf
        series_conf = os.path.join(basedir, 'series.conf')
        patches = parse_series_conf(basedir, series_conf)
        vout(4, 'patches: {}'.format(patches))

        # collect Makefile changesets from patch files
        changes = []
        for pfn in patches:
            pfn = os.path.join(patchdir, pfn)
            with open(pfn, 'r') as f:
                patch_data = f.read()
                if 'Makefile' in patch_data:
                    changeset = parse_makefiles(patch_data)
                    if changeset:
                        vout(3, 'parse_matches: {}: {}'.format(pfn, changeset))
                        changes.append(changeset)

        # iterate over all changesets, and apply them
        for changeset in changes:
            for ch in changeset:
                vout(3, '{}'.format(ch))
                src_version.update(ch['variable'], ch['value'])

        # provide the result on stdout
        stdout(src_version)

        return ret


    def main(argv = None):
        """Command line interface and console script entry point."""
        if argv is None:
            argv = sys.argv[1:]

        try:
            optlist, args = getopt.getopt(argv, 'hVvb:p:',
                ('help', 'version', 'verbose', 'basedir=', 'patches=')
            )
        except getopt.error as msg:
            exit(1, msg, True)

        for opt, par in optlist:
            if opt in ('-h', '--help'):
                exit(usage = True)
            elif opt in ('-V', '--version'):
                exit(msg = 'version {}'.format(gpar.version))
            elif opt in ('-v', '--verbose'):
                gpar.loglevel += 1
            elif opt in ('-b', '--basedir'):
                gpar.basedir = par
            elif opt in ('-p', '--patches'):
                gpar.patches = par

        # ignore broken pipe errors (SIGPIPE)
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)

        vout(3, 'started with pid {pid} in {appdir}'.format(**gpar.__dict__))
        try:
            return compute(gpar.basedir, gpar.patches)
        except (ValueError, IOError) as exc:
            stderr('Sorry, we hit a snag: {}'.format(exc))
            return 1
        except KeyboardInterrupt:
            return 3    # SIGQUIT

    if __name__ == '__main__':
        sys.exit(main())
