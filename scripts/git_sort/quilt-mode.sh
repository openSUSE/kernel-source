# Contains a set of shell functions to assist in backporting upstream commits
# to SUSE's kernel-source.git.

# Copyright (C) 2018 SUSE LLC
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301,
# USA.

_libdir=$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")
. "$_libdir"/lib.sh
. "$_libdir"/lib_tag.sh

alias q=quilt

_switcheroo () {
	if [ -r series ] &&
		head -n1 series | grep -qv "^# Kernel patches configuration file$" &&
		[ -r patches/series.conf ] &&
		head -n1 patches/series.conf | grep -q "^# Kernel patches configuration file$"; then
		ln -sf patches/series.conf series
	fi
}
_switcheroo


qfmake () {
	local i
	local doit=1
	while true ; do
		case "$1" in
			-h|--help)
				echo "Usage: ${FUNCNAME[1]} [options] [extra arguments passed to make]"
				echo ""
				echo "Build targets that have been modified by top patch (using a simple heuristic)."
				echo ""
				echo "Options:"
				echo "    -x, --exclude <target|dir>     Exclude target or targets under directory from automatic building."
				echo "    -X, --no-exclude <target|dir>  Remove previously set exclusion."
				echo "    -r, --reset                    Reset exclusion list."
				echo "    -s, --show                     Show exclusion list."
				echo "    -h, --help                     Print this help"
				return
				;;
			-x|--exclude)
				if printf "%s\n" "${qfm_excludes[@]}" | grep -qv "$2"; then
					qfm_excludes+=("$2")
				fi
				shift
				doit=
				;;
			-X|--no-exclude)
				for i in $(seq 0 $((${#qfm_excludes[@]} - 1))); do
					if [ "${qfm_excludes[i]}" = "$2" ]; then
						qfm_excludes=("${qfm_excludes[@]:0:$i}" "${qfm_excludes[@]:$((i + 1))}")
						break
					fi
				done
				shift
				doit=
				;;
			-r|--reset)
				qfm_excludes=()
				return
				;;
			-s|--show)
				if [ "${#qfm_excludes[@]}" -gt 0 ]; then
					printf "%s\n" "${qfm_excludes[@]}"
				fi
				return
				;;
			*)
				break
				;;
		esac
		shift
	done

	if [ -z "$doit" ]; then
		return
	fi

	local targets new_target
	for new_target in "$@" $(quilt --quiltrc - files | sed -n -e 's/.c$/.o/p'); do
		local exclude
		local add=1
		for exclude in "${qfm_excludes[@]}"; do
			# new_target is under exclude
			if echo "$new_target" | grep -q '^'"$exclude"; then
				add=
				break
			fi
		done
		if [ -z "$add" ]; then
			continue
		fi

		# filter targets to remove elements that are included under
		# other elements
		for i in $(seq 0 $((${#targets[@]} - 1))); do
			local target=${targets[i]}
			# new_target is under target
			if echo "$new_target" | grep -q '^'"$target"; then
				add=
				break
			# target is under new_target
			elif echo "$target" | grep -q '^'"$new_target"; then
				# remove targets[i]
				targets=("${targets[@]:0:$i}" "${targets[@]:$((i + 1))}")
			fi
		done
		if [ "$add" ]; then
			targets+=("$new_target")
		fi
	done

	if [ ${#targets[@]} -gt 0 ]; then
		make "${targets[@]}"
	fi
}


qf1 () {
	cat $(quilt --quiltrc "$_libdir"/quiltrc.qf1 top)
}


qgoto () {
	if command=$("$_libdir"/qgoto.py "$@") && [ "$command" ]; then
		quilt $command
	fi
}


qdupcheck () {
	"$_libdir"/qdupcheck.py "$@"
}


qdiffcheck () {
	local git_dir
	git_dir=$("$_libdir"/../linux_git.sh) || return 1
	local rev=$(tag_get git-commit < $(q top) | GIT_DIR=$git_dir expand_git_ref)
	interdiff <(GIT_DIR=$git_dir $_libdir/git-f1 $rev) $(q top)
}


#unset _references _destination
qcp () {
	# capture and save some options
	local r_set d_set
	local args
	while [ "$1" ] ; do
		case "$1" in
			-r|--references)
				_references=$2
				args+=($1 "$2")
				r_set=1
				shift
				;;
			-d|--destination)
				_destination=$2
				args+=($1 "$2")
				d_set=1
				shift
				;;
			*)
				args+=($1)
				;;
		esac
		shift
	done

	if [ -z "$r_set" -a "$_references" ]; then
		args=(-r "$_references" "${args[@]}")
	fi

	if [ -z "$d_set" -a "$_destination" ]; then
		args=(-d "$_destination" "${args[@]}")
	fi

	"$_libdir"/qcp.py "${args[@]}"
}


# Save -r and -d for later use by qcp
_saveopts () {
	local result=$(getopt -o hr:d: --long help,references:,destination: -n "${BASH_SOURCE[0]}:${FUNCNAME[0]}()" -- "$@")
	if [ $? != 0 ]; then
		echo "Error: getopt error" >&2
		return 1
	fi

	eval set -- "$result"

	while true ; do
		case "$1" in
			-h|--help)
				echo "Usage: ${FUNCNAME[1]} [options]"
				echo ""
				echo "Options:"
				echo "    -r, --references <value>    bsc# or FATE# number used to tag the patch file."
				echo "    -d, --destination <dir>     Destination \"patches.xxx\" directory."
				echo "    -h, --help                  Print this help"
				return 1
				;;
			-r|--references)
				_references=$2
				shift
				;;
			-d|--destination)
				_destination=$2
				shift
				;;
			--)
				shift
				break
				;;
			*)
				echo "Error: could not parse arguments" >&2
				return 1
				;;
		esac
		shift
	done
}


#unset series
qadd () {
	local git_dir
	git_dir=$("$_libdir"/../linux_git.sh) || return 1

	if [ $BASH_SUBSHELL -gt 0 ]; then
		echo "Error: it looks like this function is being run in a subshell. It will not be effective because its purpose is to set an environment variable. You could run it like this instead: \`${FUNCNAME[0]} <<< \$(<cmd>)\`." > /dev/stderr
		return 1
	fi

	if ! _saveopts "$@"; then
		return
	fi

	local _series=$(grep .)

	mapfile -t series <<< "$(
		(
			[ ${#series[@]} -gt 0 ] && printf "%s\n" "${series[@]}"
			[ -n "$_series" ] && echo "$_series"
		) | GIT_DIR=$git_dir "$_libdir"/git_sort_debug
	)"

	if [ -z "${series[0]}" ]; then
		unset series[0]
	fi
}


qedit () {
	local git_dir
	git_dir=$("$_libdir"/../linux_git.sh) || return 1

	if [ "${tmpfile+set}" = "set" ]; then
		local _tmpfile=$tmpfile
	fi

	trap '[ -n "$tmpfile" -a -f "$tmpfile" ] && rm "$tmpfile"' EXIT
	tmpfile=$(mktemp --tmpdir qedit.XXXXXXXXXX)
	[ ${#series[@]} -gt 0 ] && printf "%s\n" "${series[@]}" > "$tmpfile"

	${EDITOR:-${VISUAL:-vi}} "$tmpfile"

	mapfile -t series <<< "$(grep . "$tmpfile" |
		GIT_DIR=$git_dir $_libdir/git_sort_debug)"

	if [ -z "${series[0]}" ]; then
		unset series[0]
	fi

	rm "$tmpfile"
	if [ "${_tmpfile+set}" = "set" ]; then
		tmpfile=$_tmpfile
	else
		unset tmpfile
	fi
	trap - EXIT
}


qcat () {
	[ ${#series[@]} -gt 0 ] && printf "%s\n" "${series[@]}"
}


_strip_begin () {
	sed -re 's/^[[:space:]]+//'
}


qnext () {
	[ ${#series[@]} -gt 0 ] && echo "${series[0]}" | _strip_begin
}


qskip () {
	if [ ${#series[@]} -gt 0 ]; then
		echo "Skipped:    $(echo "${series[0]}" | _strip_begin)"
		series=("${series[@]:1}")
		if [ ${#series[@]} -gt 0 ]; then
			echo "Next:       $(echo "${series[0]}" | _strip_begin)"
		else
			echo "No more entries"
		fi
	else
		return 1
	fi
}


_stablecheck () {
	local entry=$1
	local patch=$2
	local git_dir
	git_dir=$("$_libdir"/../linux_git.sh) || return 1

	local rev=$(echo "$patch" | awk '{
		match($0, "patch-([[:digit:]]+\\.[[:digit:]]+)\\.([[:digit:]]+)(-([[:digit:]]+))?", a)
		if (a[3]) {
			print "v" a[1] "." a[2] "..v" a[1] "." a[4]
		} else {
			print "v" a[1] "..v" a[1] "." a[2]
		}
	}')
	local output=$(GIT_DIR=$git_dir git log "$rev" --pretty=tformat:%H --grep "$entry")
	local nb=$(echo "$output" | wc -l)
	if [ "$output" -a $nb -eq 1 ]; then
		echo -en "This commit was backported to a stable branch as\n\t"
		GIT_DIR=$git_dir $_libdir/git-overview -m "$output"
		echo
	elif [ $nb -gt 1 ]; then
		echo "Warning: $nb potential stable commits found:" > /dev/stderr
		GIT_DIR=$git_dir git log "$rev" --oneline --grep "$entry" > /dev/stderr
	else
		echo "Warning: no potential stable commit found." > /dev/stderr
	fi
}


qdoit () {
	local entry=$(qnext | awk '{print $1}')
	while [ "$entry" ]; do
		local command
		if ! command=$("$_libdir"/qgoto.py "$entry"); then
			echo "Error: qgoto.py exited with an error" > /dev/stderr
			return 1
		fi
		while [ "$command" ]; do
			if ! quilt $command; then
				echo "\`quilt $command\` did not complete sucessfully. Please examine the situation." > /dev/stderr
				return 1
			fi

			if ! command=$("$_libdir"/qgoto.py "$entry"); then
				echo "Error: qgoto.py exited with an error" > /dev/stderr
				return 1
			fi
		done

		local output
		if ! output=$(qdupcheck $entry); then
			echo
			echo "$output"
			echo
			local patch=$(echo "$output" | awk '/patches.kernel.org\/patch-/ {print $1}')
			if [ "$patch" ]; then
				_stablecheck "$entry" "$patch"
			fi
			echo "The next commit is already present in the series. Please examine the situation." > /dev/stderr
			return 1
		fi

		if ! qcp $entry; then
			echo "\`qcp $entry\` did not complete sucessfully. Please examine the situation." > /dev/stderr
			return 1
		fi
		series=("${series[@]:1}")

		if ! quilt push; then
			echo "The last commit did not apply successfully. Please examine the situation." > /dev/stderr
			return 1
		fi

		./refresh_patch.sh

		if ! qfmake "$@"; then
			echo "The last applied commit results in a build failure. Please examine the situation." > /dev/stderr
			return 1
		fi

		entry=$(qnext | awk '{print $1}')
	done
}
