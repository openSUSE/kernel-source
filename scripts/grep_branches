#!/bin/bash
# git grep over all branches defined by branches.conf
#
# all given arguments will be given as git grep arguments
. $(dirname "$0")/common-functions

grep_branch()
{
	local branch=$1
	shift
	local params
	local files

	# Loop through all positional parameters
	while [[ $# -gt 0 ]]; do
		if [[ "$1" == "--" ]]; then
			files=("$@")
			break
		fi
		params+=("$1")
		shift
	done

	git --no-pager grep "${params[@]}" origin/$branch "${files[@]}"
	return 0
}

# Enforce faster git grep if there is no multibyte in the input
# at least git grep -i is much faster on regexps with LC_CTYPE=C
params="$@"
if [ "${#params}" -eq $(LC_ALL=C printf '%s' "$params" | wc -c) ]
then
	unset LC_ALL
	export LC_CTYPE="C"
fi

branches_conf="$(fetch_branches $refresh)"
for_each_build_branch "$branches_conf" grep_branch "$@"
