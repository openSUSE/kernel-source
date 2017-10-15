#!/bin/bash

kernel_source=~/local/src/kernel-source/.git
configs_dest=~/suse/configs

# if we are in a checked out copy of the kernel.git or kernel-source.git repo,
# we will copy the config for the current branch to .config
if git_top_path=$(git rev-parse --show-toplevel 2>/dev/null) &&
	head=$(awk '
		/^ref:/ {
			match($2, "refs/heads/(.*)", a)
			print a[1]
			exit 0
		}
		{
			exit 1
		}
	' $git_top_path/.git/HEAD) &&
	wd_remote_name=$(git config --get branch.$head.remote) &&
	wd_remote_branch=$(git config --get branch.$head.merge | awk '
		/^refs\/heads\// {
			match($1, "refs/heads/(.*)", a)
			print a[1]
			exit 0
		}
		{
			exit 1
		}
	') &&
	url=$(git config --get "remote.$wd_remote_name.url"); then
	if echo "$url" | grep -q "/kernel-source.git$" &&
		[ -d "$git_top_path/tmp/current" ] &&
		echo "$(readlink "$git_top_path/tmp/current")" | grep -q "$wd_remote_branch$"; then
		config_dest="$git_top_path/tmp/current"
	elif echo "$url" | grep -q "/kernel.git$"; then
		config_dest=$git_top_path
	fi
fi

export GIT_DIR="$kernel_source"
while read branch; do
	ks_remote_name=$(git config --get branch.$branch.remote)
	ks_remote_branch=$(git config --get branch.$branch.merge | awk '
		/^refs\/heads\// {
			match($1, "refs/heads/(.*)", a)
			print a[1]
			exit 0
		}
		{
			exit 1
		}
	')
	if [ "$ks_remote_branch" != "$branch" ]; then
		continue
	fi
	ref="$ks_remote_name/$ks_remote_branch"
	object=$(git ls-tree $ref config/x86_64/default | awk '{print $3}')
	if [ "$object" ]; then
		do_copy=
		prefix="  "

		if [ "$config_dest" -a "$wd_remote_branch" = "$ks_remote_branch" ]; then
			do_copy=1
			prefix="* "
		fi

		echo "$prefix$ks_remote_branch"

		sanitized=$(echo "$ks_remote_branch" | sed -re 's:/:_:g')
		git cat-file blob $object > "$configs_dest/$sanitized"
		if [ "$do_copy" ]; then
			cp "$configs_dest/$sanitized" "$config_dest/.config"
		fi
	fi
done < <(git rev-parse --symbolic --branches | grep -E "^(SLE|openSUSE|cve/|stable$|master$)")
