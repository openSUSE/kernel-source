# Contains a set of shell functions to assist in generating a patch
# series from upstream commits.
# Useful when porting a list of commits from upstream to SUSE's kernel.git


_libdir=$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")
. "$_libdir"/lib.sh
. "$_libdir"/lib_tag.sh

# Read patch file names and output corresponding lines suitable for later
# processing via the "series" environment var
# _expand_am [prefix]
_expand_am () {
	local prefix

	if [ -d "$1" ]; then
		prefix=$(readlink -f "$1")
	elif [ "$1" ]; then
		echo "Error: not a directory \"$1\"" > /dev/stderr
		return 1
	fi

	local p
	while read p; do
		local f
		if [ "$prefix" ]; then
			f="$prefix/$p"
		else
			f=$p
		fi

		if [ -r "$f" ]; then
			local ref

			# do the lookup and expansion in separate steps so that
			# a missing Git-commit tag results in an error from git
			# during the expand
			if ! ref=$(cat "$f" | tag_get git-commit); then
				return 1
			fi

			if ref=$(echo "$ref" | expand_git_ref); then
				echo "$ref am $f"
			else
				return 1
			fi
		elif echo "$p" | grep -q "^[^#]"; then
			echo "Error: cannot read \"$f\"" > /dev/stderr
			return 1
		fi
	done
}

# Read commit refs and output corresponding lines suitable for later processing
# via the "series" environment var
# _expand_cp
_expand_cp () {
	local list ref

	if ! list=$(expand_git_ref); then
		return 1
	fi

	for ref in $list; do
		echo "$ref cp $ref"
	done
}

# Read lists of patches and commits and set them in a "series" environment
# variable. If no file is specified using options, read stdin as a list of
# commits to cherry-pick.
# bpset [options] [path of interest for cherry-pick...]
# Options:
#    -p, --prefix=<dir>    Search for patches in this directory
#    -a, --am=<file>       Also read a list of patches to apply from FILE 
#    -c, --cp=<file>       Also read a list of commits to cherry-pick from FILE
#    -s, --sort            Sort resulting series according to upstream order
bpset () {
	if [ $BASH_SUBSHELL -gt 0 ]; then
		echo "Error: it looks like this function is being run in a subshell. It will not be effective because its purpose is to set an environment variable. You could run it like this instead: \`${FUNCNAME[0]} <<< \$(<cmd>)\`." > /dev/stderr
		return 1
	fi

	local opt_prefix opt_sort
	local _series opts
	local result=$(getopt -o p:a:c:s --long prefix:,am:,cp:,sort -n "${BASH_SOURCE[0]}:${FUNCNAME[0]}()" -- "$@")

	if [ $? != 0 ]; then
		echo "Error: getopt error" >&2
		exit 1
	fi

	eval set -- "$result"

	while true ; do
		case "$1" in
			-p|--prefix)
				opt_prefix=$2
				shift
				;;
			-a|--am)
				if ! _series=$(echo "$_series"; cat "$2" | _expand_am "$opt_prefix"); then
					return 1
				fi
				opts=1
				shift
				;;
			-c|--cp)
				if ! _series=$(echo "$_series"; cat "$2" | _expand_cp); then
					return 1
				fi
				opts=1
				shift
				;;
			-s|--sort)
				opt_sort=1
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

	paths_of_interest=$(
		for arg in "$@"; do
			echo "$arg"
		done
	)

	# if options were empty, read from stdin
	if [ -z "$opts" ] && ! _series=$(cat | _expand_cp); then
		return 1
	fi
	if [ "$opt_sort" ]; then
		_series=$(echo "$_series" | git sort)
	fi
	series=$(echo "$_series" | cut -d" " -f 2-)
}

bpref () {
	if [ -n "$series" ]; then
		set -- $(echo "$series" | head -n1)
		case "$1" in
			cp)
				echo $2
				;;
			am)
				cat "$2" | tag_get git-commit | expand_git_ref
				;;
		esac
	fi
}

_bpaction () {
	if [ -n "$series" ]; then
		awk '{print $1; exit}' <<< "$series"
	fi
}

_bparg () {
	if [ -n "$series" ]; then
		awk '{print $2; exit}' <<< "$series"
	fi
}

# show the first entry in the series
bpnext () {
	if [ -n "$series" ]; then
		local ref=$(bpref)

		echo "$series" | head -n1
		git log -n1 --oneline $ref
	fi
}
alias bptop=bpnext

bpstat () {
	local action=$(_bpaction)

	case "$action" in
		am)
			git apply --stat < $(_bparg)
			;;
		cp)
			local ref=$(bpref)

			git diff --stat $ref^..$ref
			;;
	esac
}

bpf1 () {
	local action=$(_bpaction)

	case "$action" in
		am)
			cat $(_bparg)
			;;
		cp)
			git f1 $(bpref)
			;;
	esac
}

bpskip () {
	if [ $BASH_SUBSHELL -gt 0 ]; then
		echo "Error: it looks like this function is being run in a subshell. It will not be effective because its purpose is to set an environment variable." > /dev/stderr
		return 1
	fi
	previous=$(echo "$series" | head -n1)
	series=$(awk 'NR > 1 {print}' <<< "$series")
}

bpcherry-pick-all () {
	local action=$(_bpaction)
	local arg=$(_bparg)
	bpskip

	case "$action" in
		am)
			if git am --reject $arg; then
				bpaddtag
			else
				return $?
			fi
			;;
		cp)
			git cherry-pick -x $arg
			;;
	esac
}
alias bpcp=bpcherry-pick-all

bpaddtag () {
	local action=$(echo "$previous" | awk '{print $1}')
	local arg=$(echo "$previous" | awk '{print $2}')
	case $action in
		cp)
			git log -n1 --pretty=format:%B | \
				tag_add "cherry picked from commit" "$arg" | \
				git commit -q --amend -F -
			;;
		am)
			local ref=$(cat "$arg" | tag_get git-commit | expand_git_ref)
			local suse_ref=$(cat "$arg" | tag_get references)

			git log -n1 --pretty=format:%B | \
				tag_add "cherry picked from commit" "$ref" | \
				tag_add "cherry picked for" "$suse_ref" | \
				git commit -q --amend -F -
			;;
	esac
}

# bpcherry-pick-include <path...>
bpcherry-pick-include () {
	local args=$(
		for arg in "$@"; do
			echo "--include \"$arg\""
		done
		while read path; do
			echo "--include \"$path\""
		done <<< "$paths_of_interest"
	)
	args=$(echo "$args" | xargs -d"\n")
	local action=$(_bpaction)
	local arg=$(_bparg)
	bpskip
	case $action in
		cp)
			local patch=$(git format-patch --stdout $arg^..$arg)
			local files=$(echo "$patch" | \
				eval "git apply --numstat $args" | cut -f3)

			if echo "$patch" | eval "git apply --reject $args"; then
				echo "$files" | xargs -d"\n" git add 
				git commit -C $arg
				bpaddtag
			fi
			;;
		am)
			if git am --reject $args "$arg"; then
				bpaddtag
			fi
			;;
	esac
}
alias bpcpi=bpcherry-pick-include

bpreset () {
	git reset --hard
	git ls-files -o --exclude-standard | xargs rm
}
alias bpclean=bpreset

# Check that the patch passed via stdin touches only paths_of_interest
_poicheck () {
	local args=$(
		while read path; do
			echo "--exclude \"$path\""
		done <<< "$paths_of_interest"
	)
	args=$(echo "$args" | xargs -d"\n")

	eval "git apply --numstat $args" | wc -l | grep -q "^0$"
}

_jobsnb=$(($(cat /proc/cpuinfo | grep "^processor\>" | wc -l) * 2))

bpdoit () {
	if [ $# -lt 1 ]; then
		echo "If you want to do it, you must specify build paths!" > /dev/stderr
		echo "Usage: ${FUNCNAME[0]} <build path>..." > /dev/stderr
		return 1
	fi

	while [ $(bpref) ]; do
		if [ "$(_bpaction)" = "cp" ] && ! git format-patch --stdout $(bpref)^..$(bpref) | _poicheck; then
			echo "The following commit touches paths outside of the paths of interest. Please examine the situation." > /dev/stderr
			bpnext > /dev/stderr
			return 1
		fi

		if ! bpcp; then
			echo "The last commit did not apply successfully. Please examine the situation." > /dev/stderr
			return 1
		fi

		local prev_action=$(echo "$previous" | awk '{print $1}')
		# When doing many am in sequence, only build test at the end
		if ! [ "$prev_action" = "am" -a "$(_bpaction)" = "am" ] &&
			! make -j$_jobsnb "$@"; then
			echo "The last applied commit results in a build failure. Please examine the situation." > /dev/stderr
			return 1
		fi
	done
}
