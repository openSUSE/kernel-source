import configparser

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

def read_config_sh(file = 'rpm/config.sh'):
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
