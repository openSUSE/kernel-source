#!/bin/bash

# Check if a commit is referenced in the log of later commits.
# Useful to identify missing followup commits.


progname=$(basename "$0")
usage () {
	echo "Usage: $progname [OPTIONS]"
	echo ""
	cat <<"EOD"
Read a list of git hashes from stdin and print information about commits which
reference these hashes in their log and which are not part of the list.

The input list must be partially ordered such that if it already contains some
fixes, they appear after the commit they fix. Otherwise, fixes may appear
multiple times in the output. Use `git sort` if needed.

Options:
	-h                      Print this help
EOD
}

while getopts ":h" opt; do
	case $opt in
		h)
		  usage
		  exit 0
		  ;;
		?)
		  echo "Invalid option: -$OPTARG" >&2
		  exit 1
		  ;;
	esac
done

indent="    "
declare -a known
tac | while read line; do
	commit=$(git rev-parse --short=7 $(echo "$line" | awk '{print $1}'))
	git log --no-merges --pretty="$indent%h %s" --grep="$commit" $commit.. | \
		grep -vf <(echo -n "${known[@]}" | \
		awk 'BEGIN {RS=" "} {print "^'"$indent"'" $1}')
	known+=("$commit")
	echo "$line"
done | tac
