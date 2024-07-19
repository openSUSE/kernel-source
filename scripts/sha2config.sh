#!/bin/bash
GIT="git --git-dir=${LINUX_GIT:-.}/.git"

while [ $# -gt 0 ]
do
	sha=$1
	shift
	sha_summary="$($GIT show -s --pretty='format:%h ("%s")' $sha 2>/dev/null)"
	if [ $? -gt 0 ]
	then
		echo $sha invalid >&2
		continue
	fi
	echo "* $sha_summary"
	for file in $($GIT show --pretty="" --name-only $sha)
	do
		echo -n "$file "
		case $file in
			*.c)
				./file2config.sh $file || echo "no parla"
				;;
			*)
				echo "no parla"
		esac
	done
done
