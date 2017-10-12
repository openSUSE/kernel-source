#!/bin/bash -e

# Transform a "Git-commit" tag into a "(cherry picked from ...)" line.
# Useful when importing patches from SUSE's kernel-source.git into
# kernel.git.


progname=$(basename "$0")
libdir=$(dirname "$(readlink -f "$0")")
filename=

. "$libdir"/lib_tag.sh

usage () {
	echo "Usage: $progname [options] [patch file]"
	echo ""
	echo "Options:"
	printf "\t-h, --help              Print this help\n"
	echo ""
}


result=$(getopt -o h --long help -n "$progname" -- "$@")

if [ $? != 0 ]; then
	echo "Error: getopt error" >&2
	exit 1
fi

eval set -- "$result"

while true ; do
        case "$1" in
                -h|--help)
					usage
					exit 0
					;;
                --)
					shift
					break
					;;
                *)
					echo "Error: could not parse arguments" >&2
					exit 1
					;;
        esac
	shift
done

# bash strips trailing newlines in variables, protect them with "---"
if [ -n "$1" ]; then
	filename=$1
	patch=$(cat $1 && echo ---)
	shift
else
	patch=$(cat && echo ---)
fi

if [ -n "$1" ]; then
	echo "Error: too many arguments" > /dev/stderr
	usage > /dev/stderr
	exit 1
fi

body=$(echo -n "${patch%---}" | awk -f "$libdir"/patch_body.awk && echo "---")
header=$(echo -n "${patch%---}" | awk -f "$libdir"/patch_header.awk && echo "---")

git_commit=$(echo "$header" | tag_get git-commit | awk '{print $1}')
if [ "$git_commit" ]; then
	header=$(echo -n "$header" | tag_add "cherry picked from commit" "$git_commit")
fi

if [ -n "$filename" ]; then
	exec 1>"$filename"
fi
echo -n "${header%---}"
echo -n "${body%---}"
