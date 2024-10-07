#!/usr/bin/env python3

import re

from pathlib import Path, PurePath
from os import chdir
from argparse import ArgumentParser
from os.path import expanduser


def _load_makefile(make_file: str) -> list:

    try:
        with open(make_file) as file:
            buffer = file.read()
    except FileNotFoundError:
        return []

    joined = re.sub(r'\\\s*\n[^:]', ' ', buffer)

    lines = joined.split('\n')

    return lines


def _sanitize_config(target):
    config = target.strip('+=').strip().strip('obj-$(){}:').strip()
    return config


def _find_config(obj_path, deep):

    if deep > 10:
        return None

    make_file = Path(obj_path.parent, "Makefile")

    lines = _load_makefile(make_file)

    obj_name = PurePath(obj_path).name
    for line in lines:
        sep = line.split()
        if obj_name not in sep:
            continue

        # target found, check if this one with config
        target = sep[0]
        if target.startswith('obj-'):
            return _sanitize_config(target)

        # target contains another object file rule, so strip it would and try
        # again
        try:
            target, _ = target.rsplit('-', 1)
        except ValueError as ve:
            # print(ve)
            continue

        return _find_config(Path(obj_path.parent, target + '.o'), deep + 1)


def find_configs_for_files(linux_dir: str, file_paths: list):

    configs = dict()
    build_ins = []
    missing = []

    if not file_paths:
        return configs, build_ins, missing

    try:
        chdir(expanduser(linux_dir))
    except OSError as os_err:
        print(os_err)
        return configs, build_ins, missing

    for path in file_paths:
        path = path.strip()
        obj_file = path.replace('.c', '.o')
        config = _find_config(Path(obj_file), 0)
        if not config:
            missing.append(path)
        elif config == 'y' or config == 'm':
            build_ins.append(path)
        elif config.startswith('CONFIG_'):
            configs[path] = config
        # else there is garbage like 'subst', 'vds' for wrongly parsed input

    return configs, build_ins, missing


if __name__ == '__main__':

    description = 'Show which CONFIG_ option enable this file'
    parser = ArgumentParser(description=description)

    help = 'Linux source tree directory'
    parser.add_argument('--linux', type=str, required=True, help=help)
    parser.add_argument('--skip-missing', action='store_true')
    parser.add_argument('--verbose', action='store_true')
    parser.add_argument('filename', nargs='+')

    args = parser.parse_args()

    configs, build_ins, missing = find_configs_for_files(
        args.linux, args.filename)

    if not args.verbose:
        for file_name in configs:
            print(configs[file_name])
    else:
        for file_name in configs:
            config = configs[file_name]
            print('{:32} {}'.format(config, file_name))

        if not args.skip_missing:
            print('\nCan not find configuration for these files:')

            for file_name in missing:
                print(file_name)
