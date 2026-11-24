#!/usr/bin/python3
import sys
if sys.version_info < (3, 6):
    raise RuntimeError('python 3.6 or later required')

"""
Synopsis: determine the current kernel source version from a series of patches
          as being referenced from series.conf

Usage: {appname} [-hVp:]
       -h, --help           this message
       -V, --version        print version and exit
       -p, --patches dir    directory, where patches.* reside, referenced in
                            series.conf [default: '{patchdir}']
                            series.conf is read from . and config.sh from
                            the directory from which {appname} is executed

Description:
The executable part of this script replaces the old compute-PATCHVERSION.sh
script. It is expected to be executed in the kernel-source base folder, e.g.:

        ./rpm/compute-PATCHVERSION.py

Otherwise provide the --patches argument with the preferred base directory.

This file is typically a symlink to ../scripts/python/kutil/config.py.

It fetches the kernel source version from config.sh, then parses the
./series.conf file, collecting all patch files, and tracks any changes of the
top level Makefile to the four version defining symbols: VERSION, PATCHLEVEL,
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
# disable some pylint noise
# pylint: disable=line-too-long, missing-function-docstring, unspecified-encoding
# pylint: disable=consider-using-f-string, consider-using-sys-exit

from typing import cast, Any, List, Iterable, TypeVar, Union, Mapping, Dict, Iterator, Tuple, Optional, Sequence, NoReturn
try:
    from _typeshed import SupportsKeysAndGetItem
    DSI = Union[SupportsKeysAndGetItem[str, str], Iterable[Tuple[str, str]]]
except:
    DSI = Union[Mapping[str, str], Iterable[Tuple[str, str]]]  # type: ignore[misc]
import configparser
import subprocess
import shlex
import re
import os

# some commonly used functions

T = TypeVar('T')
BytesStr = Union[bytes, str]

def uniq(lst: Sequence[T]) -> Sequence[T]:
    # fairly slow but does not require any special property of elements nor ordered dictionaries
    return [x for i, x in enumerate(lst) if i == lst.index(x)]

def init_repo(tmpdirname: str, repo: str, branch: str) -> str:
    subprocess.check_call(['git', 'init', '-q', '--object-format=sha256', '-b', branch, repo], cwd=tmpdirname)
    return os.path.join(tmpdirname, repo)

def get_source_timestamp(directory: str) -> str:
    with open(os.path.join(directory, 'source-timestamp'), 'r') as fd:
        source_timestamp = fd.read().splitlines()
    return '\n'.join(source_timestamp[1:] + [source_timestamp[0]])

def list_files(directory: str) -> Sequence[str]:
    if len(directory) > 1:
        directory = directory.rstrip('/')
    result = []
    for root, _, filenames in os.walk(directory):
        for f in filenames:
            result.append(os.path.join(root, f)[len(directory)+1:])
    return sorted(result)

def list_specs(directory: str) -> Sequence[str]:
    ext = '.spec'
    return [f[0:-len(ext)] for f in list_files(directory) if f.endswith(ext)]

def read_source_timestamp(directory: str) -> Mapping[str, str]:
    file = os.path.join(directory, 'source-timestamp')
    cp = configparser.ConfigParser(delimiters=(':'), interpolation=None)
    with open(file, 'r') as fd:
        cp.read_string('[section]\nDate: ' + fd.read())
    config = cp['section']
    return config

class SrcVersion:
    """Class, defining a source code version, allows parsing from string, updating single values
    and returns the resulting version as string repr"""
    def __init__(self, version_str: str):
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

    def update(self, part:str, value:str) -> None:
        """Update a specific version component to a new value"""
        if part in self._partlist:
            setattr(self, part, value)

    def __str__(self) -> str:
        return '{version}.{patchlevel}.{sublevel}{extraversion}'.format(**self.__dict__)

    def __iter__(self) -> Iterator[Tuple[str, str]]:
        for index, item in self.__dict__.items():
            if index in self._partlist:
                yield index, item

class CaseInsensitiveDict(Dict[str, str]):
    def __init__(self, *args: DSI, **kwargs: str):
        self.update(*args, **kwargs)

    def __getitem__(self, key: str) -> str:
        return super().__getitem__(key.casefold())

    def __setitem__(self, key: str, value: str) -> None:
        return super().__setitem__(key.casefold(), value)

    def __contains__(self, key: Any) -> bool:
        return isinstance(key, str) and super().__contains__(key.casefold())

    # https://github.com/python/mypy/issues/3737
    def get(self, key: str, default: T = None) -> Union[str, T]:  # type: ignore[assignment]
        return super().get(key.casefold(), default)

    def update(self, *args: DSI, **kwargs: str) -> None:
        for k, v in dict(*args, **kwargs).items():
            self[k] = v

    def getboolean(self, key: str) -> bool:
        if not key.casefold() in self:
            return False
        value = self.get(key)
        if value.isdigit():
            if int(value) == 0:
                return False
            return True
        if value.casefold() in ['y', 'yes', 't', 'true']:
            return True
        if value.casefold() in ['n', 'no', 'f', 'false']:
            return False
        raise ValueError('Do not know how to interpret "%s" as boolean' % (value,))

    def getversion(self, key: str) -> SrcVersion:
        return SrcVersion(self.get(key))


def read_config_sh(package_tar_up_dir: str) -> CaseInsensitiveDict:
    """Parse config.sh file and return a dict with key value pairs"""
    config_sh = os.path.join(package_tar_up_dir, 'config.sh')
    with open(config_sh, 'rb') as f:
        data = f.read()
    return read_config_sh_data(data, config_sh)


def read_config_sh_data(data: BytesStr, filename: Optional[str] = None) -> CaseInsensitiveDict:
    config = CaseInsensitiveDict()
    lnnr = 0
    if isinstance(data, bytes):
        data = data.decode(errors='replace')
    for line in data.splitlines():
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
            raise ValueError('line {} malformed in {}: "{}"'.format(lnnr, filename, line))

    return config

def get_kernel_project_package(package_tar_up_dir: str) -> Tuple[str, str]:
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

def get_kernel_projects(package_tar_up_dir: str) -> Mapping[str, Mapping[str, str]]:
    rpm_config = read_config_sh(package_tar_up_dir)
    ibs_projects: Dict[str, str] = {}
    obs_projects: Dict[str, str] = {}
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
def get_package_archs(package_tar_up_dir: str, limit_packages: Optional[Iterable[str]] = None) -> Iterable[str]:
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

def parse_series_conf(patchdir: BytesStr, series_conf: BytesStr) -> Iterable[str]:
    """Parse the series.conf file, taking guards into account, and return a list of patch files"""
    # Use grep to extract patch file names from series.conf.
    # In a plain quilt series file the non-whitespace thing at the start of a line that is not a comment is
    # a patch filename. However, the series.conf in kernel-source may contain 'guards'. While complex semantic
    # of guards was supported in the past in practice guards are alos comments.
    # Ignore anything that does not look like a patch filename.
    pipe = subprocess.Popen(['grep', '-o', '^[ \t]*patches[.][^ \t#]*', series_conf],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    patches, errors = pipe.communicate()
    if pipe.returncode == 2:
        raise RuntimeError('%r\n%r' % (pipe.args, errors))
    # The resulting patch filenames can be prefixed with whitespace.
    # However, they are fed to xargs which splits on whitespace conveniently stripping the leading whitespace
    # from the patch filenames. This alleviates the need to ever touch the buffer from python
    pipe = subprocess.Popen(['xargs', 'grep', '-lE', '^[+][+][+][^/]+/Makefile'],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=patchdir)
    output, errors = pipe.communicate(input=patches)
    if errors:  # The return value from xargs grep is fairly meaningless but stderr should be empty
        raise RuntimeError('%r\n%r' % (pipe.args, errors))
    patchlist = [p.decode() for p in output.splitlines()]

    return patchlist

def parse_makefiles(diff_text: str) -> Iterable[Mapping[str, str]]:
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
            in_makefile = bool(makefile_target.match(line))

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

def compute_patchversion(bindir: str, rpmdir: str, patchdir: str) -> SrcVersion:
    """Compute patchversion from config.sh, series.conf and patch files"""
    patchdir = str(patchdir)
    if not os.path.isdir(patchdir):
        raise FileNotFoundError('patch directory {} not found'.format(patchdir))

    # fetch key, value pairs from config.sh
    config = read_config_sh(bindir)

    # determine kernel base source code version
    src_version = config.getversion('srcversion')

    # fetch patch files from series.conf
    series_conf = os.path.join(rpmdir, 'series.conf')
    patches = parse_series_conf(patchdir, series_conf)

    # collect top level Makefile changesets from patch files
    changes = []
    for patch in patches:
        patch = os.path.join(patchdir, patch)
        with open(patch, 'r') as f:
            patch_data = f.read()
            changeset = parse_makefiles(patch_data)
            if changeset:
                changes.append(changeset)

    # iterate over all changesets, and apply them
    for changeset in changes:
        for ch in changeset:
            src_version.update(ch['variable'], ch['value'])

    return src_version

if __name__ == "__main__":
    import sys
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
        pid = os.getpid()
        version = __version__
        company = __company__
        author = __author__
        license = __license__
        rpmdir = '.'
        patchdir = '.'

    def stdout(*msg: str) -> None:
        print(*msg, file = sys.stdout, flush = True)

    def stderr(*msg: str) -> None:
        print(*msg, file = sys.stderr, flush = True)

    def exit(ret: int = 0, msg: Optional[Any] = None, usage: bool = False) -> NoReturn:
        """Terminate process with optional message and usage"""
        if msg:
            stderr('{}: {}'.format(gpar.appname, msg))
        if usage:
            stderr(__doc__.format(**gpar.__dict__))
        sys.exit(ret)

    def main(argv: Optional[Sequence[str]] = None) -> int:
        """Command line interface and console script entry point."""
        if argv is None:
            argv = sys.argv[1:]

        try:
            optlist, _ = getopt.getopt(argv, 'hVvp:',
                ('help', 'version', 'verbose', 'patches=')
            )
        except getopt.error as msg:
            exit(1, msg, True)

        for opt, par in optlist:
            if opt in ('-h', '--help'):
                exit(usage = True)
            elif opt in ('-V', '--version'):
                exit(msg = 'version {}'.format(gpar.version))
            elif opt in ('-p', '--patches'):
                gpar.patchdir = par

        # ignore broken pipe errors (SIGPIPE)
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)

        try:
            stdout(str(compute_patchversion(gpar.appdir, gpar.rpmdir, gpar.patchdir)))
            return 0
        except (ValueError, IOError, OSError, RuntimeError) as exc:
            stderr('Sorry, we hit a snag: {}'.format(exc))
            return 1
        except KeyboardInterrupt:
            return 3    # SIGQUIT

    sys.exit(main())
