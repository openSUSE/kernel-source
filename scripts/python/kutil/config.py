import configparser
import subprocess
import os

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

def read_source_timestamp(file):
    cp = configparser.ConfigParser(delimiters=(':'), interpolation=None)
    with open(file, 'r') as fd:
        cp.read_string('[section]\nDate: ' + fd.read())
    config = cp['section']
    return config

def read_config_sh(file):
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
    rpm_config = read_config_sh(os.path.join(package_tar_up_dir, 'config.sh'))
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
    config_filename = os.path.join(package_tar_up_dir, 'config.sh')
    rpm_config = read_config_sh(config_filename)
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
