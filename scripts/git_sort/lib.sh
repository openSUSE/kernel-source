bash_single_esc () {
	sed "s/'/'\\\\''/g"
}

# var_override [options] <var name> <value> <source name>
# Options:
#    -a, --allow-empty    Allow an empty "value" to override the value of "var"
var_override () {
	local result=$(getopt -o a --long allow-empty -n "${BASH_SOURCE[0]}:${FUNCNAME[0]}()" -- "$@")
	local opt_empty

	if [ $? != 0 ]; then
		echo "Error: getopt error" >&2
		exit 1
	fi

	eval set -- "$result"

	while true ; do
		case "$1" in
			-a|--allow-empty)
						opt_empty=1
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

	local name=$1
	local value=$2
	local value_esc=$(echo "$value" | bash_single_esc)
	local src=$3
	local src_esc=$(echo "$src" | bash_single_esc)

	if [ -n "$value" -o "$opt_empty" ]; then
		local name_src=_${name}src
		if [ -z "${!name}" ]; then
			eval "$name='$value_esc'"
			eval "$name_src='$src_esc'"
		elif [ "$value" != "${!name}" ]; then
			if [ "${!name_src}" ]; then
				echo "Warning: $src (\"$value\") and ${!name_src} (\"${!name}\") differ. Using $src." > /dev/stderr
			fi
			eval "$name='$value_esc'"
			eval "$name_src='$src_esc'"
		fi
	fi
}

# expand_git_ref [options]
# Options:
#    -q, --quiet          Do not error out if a refspec is not found, just print an empty line
expand_git_ref () {
	local result=$(getopt -o q --long quiet -n "${BASH_SOURCE[0]}:${FUNCNAME[0]}()" -- "$@")
	local opt_quiet

	if [ $? != 0 ]; then
		echo "Error: getopt error" >&2
		exit 1
	fi

	eval set -- "$result"

	while true ; do
		case "$1" in
			-q|--quiet)
						opt_quiet=1
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

	local commit rest
	# take the first word only, which will discard cruft like "(partial)"
	while read commit rest; do
		local hash
		local cmd="git log -n1 --pretty=format:%H '$commit' --"
		if [ -z "$opt_quiet" ] && ! hash=$(eval "$cmd"); then
			return 1
		else
			hash=$(eval "$cmd" 2>/dev/null || true)
		fi
		echo $hash
	done
}

# remove_subject_annotation
remove_subject_annotation () {
	sed -re 's/^( *\[[^]]*\] *)+//'
}

# get_patch_num
get_patch_num () {
	sed -nre 's/.*\[.*\b0*([0-9]+)\/[0-9]+\].*/\1/p'
}

# format_sanitized_subject
# Transform a subject into a file name
format_sanitized_subject () {
	sed -re '
		s/\.+/./g
		s/[^a-zA-Z0-9._]+/-/g
		s/^-+//
		s/[-.]+$//
		s/(.{,52}).*/\1/
	'
}

# cheat_diffstat
# Adds fake content to a patch body so that diffstat will show something for
# renames
cheat_diffstat () {
	awk '
		BEGIN {
			state = 0
			percent = "unknown%"
		}

		state == 4 {
			print "@@ -1 +1 @@"
			print "-" percent " of the content"
			print "+" percent " of the content"

			percent = "unknown%"
			state = 0
		}

		state == 3 && /^rename to/ {
			state = 4
		}

		state == 2 && /^rename from/ {
			state = 3
		}

		state == 1 && /^similarity index/ {
			state = 2
			percent = $3
		}

		state == 0 && /^diff --git/ {
			state = 1
		}

		{
			print
		}
	'
}
