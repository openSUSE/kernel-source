#!/usr/bin/python3
# -*- coding: utf-8 -*-

import argparse
import re

import git_sort


proto_match = re.compile("^(git|https?)://")
invalid_match = re.compile("~")
ext = ".git"


def transform(name):
    name = proto_match.sub("", name, 1)
    name = invalid_match.sub("_", name)
    if name.endswith(ext):
        name = name[:-1 * len(ext)]

    return name


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Print commands to clone the mainline Linux repository "
        "and add all remotes configured for git-sort. That repository can "
        "then be used as an ultimate reference for patch ordering in "
        "series.conf.")
    parser.add_argument("directory", nargs="?", default="linux",
                        help="Directory name to clone into. Default: linux")
    args = parser.parse_args()

    print("git clone %s %s" % (repr(git_sort.remotes[0].repo_url),
                               args.directory,))
    print("cd %s" % (args.directory,))
    repo_urls = []
    for head in git_sort.remotes[1:]:
        repo_url = head.repo_url
        if repo_url not in repo_urls:
            repo_urls.append(repo_url)
    print("\n".join(["git remote add --no-tags %s %s" % (
        transform(str(repo_url)), repr(repo_url),)
        for repo_url in repo_urls]))
    print("git fetch --all")
