#!/bin/bash

# Check if a commit is already part of a patch in SUSE's kernel-source.git
# Useful to check if a list of commits have already been backported.


progname=$(basename "$0")
libdir=$(dirname "$(readlink -f "$0")")
git_dir=$("$libdir"/../linux_git.sh) || exit 1

usage () {
	echo "Usage: $progname [paths of interest...]"
	echo ""
	echo "Read git references from stdin and check if a patch (present in "
	echo "\"series.conf\") applies the part of the related commit that is below"
	echo "the \"paths of interest\"."
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

if [ ! -r "series.conf" ]; then
	echo "Error: \"series.conf\" file could not be read. Are you at the base of a kernel-source.git tree?" > /dev/stderr
	exit 1
fi

for arg in "$@"; do
	includeargs+="--include=\"$arg\" "
done

series=$(
	while read file rest; do
		if [ -r "$file" ]; then
			echo "$file"
		fi
	done < "series.conf"
)

while read line; do
	set $line
	ref=$1
	orig_stat_nb=$(GIT_DIR=$git_dir git format-patch --stdout -n1 $ref | eval git apply --numstat "$includeargs" | wc -l)
	found=
	while read patch; do
		if [ ! "$patch" ]; then
			continue
		fi
		patch_stat_nb=$(eval git apply --numstat "$includeargs" < "$patch" | wc -l)
		if grep -q "$patch" <<< "$series" && [ "$orig_stat_nb" = "$patch_stat_nb" ]; then
			found=1
			break
		fi
	done <<< "$(git grep -li "^git-commit: $ref")"

	if [ "$found" ]; then
		echo -n "* "
	else
		echo -n "  "
	fi
	echo "$line"
done
