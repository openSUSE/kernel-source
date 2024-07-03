#!/bin/bash

# Checks whether patches matching given pattern are released for given
# branches
# Usage:
# scripts/check-patch-released.sh pattern BRANCH1[ BRANCH2 ... BRANCHN]
# E.g.
# ./scripts/check-patch-released.sh CVE-XXXX-YYYY BRANCHES
# Output
# BRANCH does not match pattern
# if no patch with the given pattern is found
# 
# $BRANCH $SHA $PATCH_FILE unreleased
# there is a patch matching introduced by $SHA in $PATCH_FILE but not released yet
#
# $BRANCH $SHA $PATCH_FILE released in rpm-$VER-$PROD-update
# there is a patch matching introduced by $SHA in $PATCH_FILE reachable from rpm-$VER-$PROD-update tag
metadata="$1"
shift

while [ $# -gt 0 ]
do
	branch=$1
	prod="$(echo $branch | tr "[:upper:]" "[:lower:]")"
	shift

	found=0
	for file in $(git grep -l "$metadata" origin/$branch | grep -v -E "patches.kabi|series.conf" | cut -d: -f2)
	do
		found=1
		sha=$(git log --reverse --oneline origin/$branch -- $file | head -n1 | cut -d" " -f1) 
		release="$(git describe --contains --match "rpm-*$prod-updates" $sha 2>/dev/null)"

		echo -n "$branch $sha $file "
		if [ -z "$release" ]
		then
			echo "unreleased"
		else
			echo "released in ${release}"
		fi
	done
	[ $found -eq 0 ] && echo "$branch does not match $metadata"
done
