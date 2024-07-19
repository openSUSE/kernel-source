#!/bin/bash

GIT="git --git-dir=${LINUX_GIT:-.}/.git"
arg=$1
file=${arg##*/}
file_obj=${file/.c/.o}
dir=${arg%/*}

makefile_target()
{
	make=$1
	obj=$2

	$GIT show origin/master:$make | while read
	do
		# handle multilines
		echo $REPLY 
	done | grep $obj | awk '{print $1}'
}

while true
do
	[ -z "$dir" -o "$dir" = "$file_obj" ] && break

	makefile=$dir/Makefile
	target="$(makefile_target $makefile $file_obj)"
	if [ -z "$target" ]
	then
		echo $file_obj not found >&2
		exit 1
	fi
	case $target in
		*CONFIG* )
			echo $makefile:$target
			exit 0
			;;
		*)
			# Go level up and look for the current dir as a target
			file_obj=${dir##*/}
			dir=${dir%/*}
	esac
done
exit 1
