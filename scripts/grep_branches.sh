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

branches_conf="$(fetch_branches $refresh)"
for_each_build_branch "$branches_conf" grep_branch "$@"
