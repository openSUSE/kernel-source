import configparser
import os

def list_files(directory):
    if len(directory) > 1:
        directory = directory.rstrip('/')
    result = []
    for root, dirs, filenames in os.walk(directory):
        for f in filenames:
            result.append(os.path.join(root, f)[len(directory)+1:])
    return sorted(result)

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
    ext = '.spec'
    lst = list_files(package_tar_up_dir)
    lst = [f for f in lst if f.endswith(ext)]
    assert len(lst) == 1
    specname = lst[0]
    assert '/' not in specname
    specname = specname[0:-len(ext)]
    return (project, specname)
