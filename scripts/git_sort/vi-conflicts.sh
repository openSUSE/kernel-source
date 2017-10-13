#!/bin/bash

while read file; do
	orig=${file%.rej}
	if [ -e "$orig" ]; then
		args+=("$orig" "$file")
	fi
done <<< "$(find ./ -name "*.rej")"

git_unmerged=$(git ls-files --unmerged | awk '{print $4}' | uniq)
if [ "$git_unmerged" ]; then
	args+=($git_unmerged)
	extra_arg='+/^[<=>]\{7}'
fi

quilt_unmerged=".pc/merge-conflicts"
if [ -f "$quilt_unmerged" ]; then
	args+=($(cat "$quilt_unmerged"))
	extra_arg='+/^[<=>]\{7}'
fi

if [ "$args" ]; then
	vi -p "${args[@]}" $extra_arg
fi
