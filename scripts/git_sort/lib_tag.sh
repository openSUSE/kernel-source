# countkeys <key>
countkeys () {
	local key=$1

	case "${key,,*}" in
	"cherry picked from commit" | "cherry picked for")
		grep "^($key .*)$" | wc -l
		;;
	*)
		grep -i "^$key: " | wc -l
		;;
	esac
}

# tag_get [options] <key>
# Options:
#    -l, --last           Do not error out if a tag is present more than once,
#                         return the last occurrence
tag_get () {
	local result=$(getopt -o l --long last -n "${BASH_SOURCE[0]}:${FUNCNAME[0]}()" -- "$@")
	local opt_last

	if [ $? != 0 ]; then
		echo "Error: getopt error" >&2
		exit 1
	fi

	eval set -- "$result"

	while true ; do
		case "$1" in
			-l|--last)
						opt_last=1
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

	local key=$1

	local header=$(cat)
	local nb=$(countkeys "$key" <<< "$header")
	if [ $nb -gt 1 -a -z "$opt_last" ]; then
		echo "Error: key \"$key\" present more than once." > /dev/stderr
		exit 1
	fi

	case "${key,,*}" in
	subject)
		awk --assign nb="$nb" '
			BEGIN {
				insubject = 0
			}

			tolower($1) ~ /subject:/ {
				nb--
				if (nb > 0) {
					next
				}
				insubject = 1
				split($0, array, FS, seps)
				result = substr($0, 1 + length(seps[0]) + length(array[1]) + length(seps[1]))
				next
			}

			insubject && /^[ \t]/ {
				sub("[ \t]", " ")
				result = result $0
				next
			}

			insubject {
				print result
				exit
			}
		' <<< "$header"
		;;
	"cherry picked from commit" | "cherry picked for")
		awk --assign nb="$nb" '
		/^\('"$key"' .*\)$/ {
				nb--
				if (nb > 0) {
					next
				}
				match($0, "^\\('"$key"' (.*)\\)$", a)
				print a[1]
				exit
			}
		' <<< "$header"
		;;
	*)
		awk --assign nb="$nb" '
			tolower($1) ~ /'"${key,,*}"':/ {
				nb--
				if (nb > 0) {
					next
				}
				split($0, array, FS, seps)
				print substr($0, 1 + length(seps[0]) + length(array[1]) + length(seps[1]))
				exit
			}
		' <<< "$header"
		;;
	esac
}

# tag_remove [options] <key>
# Options:
#    -l, --last           Do not error out if a tag is present more than once,
#                         extract the last occurrence
tag_remove () {
	local result=$(getopt -o l --long last -n "${BASH_SOURCE[0]}:${FUNCNAME[0]}()" -- "$@")
	local opt_last

	if [ $? != 0 ]; then
		echo "Error: getopt error" >&2
		exit 1
	fi

	eval set -- "$result"

	while true ; do
		case "$1" in
			-l|--last)
						opt_last=1
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

	local key=$1

	local header=$(cat && echo ---)
	local nb=$(countkeys "$key" <<< "$header")
	if [ $nb -gt 1 -a -z "$opt_last" ]; then
		echo "Error: key \"$key\" present more than once." > /dev/stderr
		exit 1
	fi

	case "${key,,*}" in
	subject)
		echo -n "${header%---}" | awk --assign nb="$nb" '
			BEGIN {
				insubject = 0
			}

			tolower($1) ~ /subject:/ {
				nb--
				if (nb == 0) {
					insubject = 1
					next
				}
			}

			insubject && /^ / {
				next
			}

			insubject {
				insubject = 0
			}

			{
				print
			}
		'
		;;
	"cherry picked from commit" | "cherry picked for")
		echo -n "${header%---}" | awk --assign nb="$nb" '
		/^\('"$key"' .*\)$/ {
				nb--
				if (nb == 0) {
					next
				}
			}

			{
				print
			}
		'
		;;
	*)
		echo -n "${header%---}" | awk --assign nb="$nb" '
			tolower($1) ~ /'"${key,,*}"':/ {
				nb--
				if (nb == 0) {
					next
				}
			}

			{
				print
			}
		'
		;;
	esac
}

# tag_add [options] <key> <value>
# Options:
#    -l, --last           Do not error out if a tag is already present, add it
#                         after the last occurrence
tag_add () {
	local result=$(getopt -o l --long last -n "${BASH_SOURCE[0]}:${FUNCNAME[0]}()" -- "$@")
	local opt_last

	if [ $? != 0 ]; then
		echo "Error: getopt error" >&2
		exit 1
	fi

	eval set -- "$result"

	while true ; do
		case "$1" in
			-l|--last)
						opt_last=1
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

	local key=$1
	local value=$2

	case "${key,,*}" in
	from)
		local header=$(cat && echo ---)
		local nb=$(countkeys "$key" <<< "$header")
		if [ $nb -gt 0 -a -z "$opt_last" ]; then
			echo "Error: key \"$key\" already present." > /dev/stderr
			exit 1
		fi

		echo -n "${header%---}" | awk --assign key="$key" --assign value="$value" --assign nb="$nb" '
			BEGIN {
				inserted = 0
			}

			NR == 1 && /^From [0-9a-f]+/ {
				print
				next
			}

			nb == 0 && !inserted {
				print key ": " value
				print
				inserted = 1
				next
			}

			tolower($1) ~ /'"${key,,*}"':/ {
				nb--
			}

			{
				print
			}
		'
		;;
	date | subject)
		local header=$(cat && echo ---)
		local nb=$(countkeys "$key" <<< "$header")
		if [ $nb -gt 0 ]; then
			echo "Error: key \"$key\" already present." > /dev/stderr
			exit 1
		fi

		local -A prevkey=(["date"]="from" ["subject"]="date")

		nb=$(countkeys "${prevkey[${key,,*}]}" <<< "$header")

		echo -n "${header%---}" | awk --assign key="$key" --assign value="$value" --assign nb="$nb" '
			{
				print
			}

			tolower($1) ~ /'"${prevkey[${key,,*}]}"':/ {
				nb--
				if (nb == 0) {
					print key ": " value
				}
			}
		'
		;;
	patch-mainline | git-repo | git-commit | references)
		local header=$(cat && echo ---)
		local nb=$(countkeys "$key" <<< "$header")
		if [ $nb -gt 0 -a -z "$opt_last" ]; then
			echo "Error: key \"$key\" already present." > /dev/stderr
			exit 1
		fi

		echo -n "${header%---}" | awk '
			BEGIN {
				added = 0
				keys["Patch-mainline:"] = 1
				keys["Git-repo:"] = 2
				keys["Git-commit:"] = 3
				keys["References:"] = 4
			}

			function keycmp(key1, key2) {
				return keys[key1] - keys[key2]
			}
			
			$1 in keys && !added {
				if (keycmp("'"$key"':", $1) < 0) {
					print "'"$key"': '"$value"'"
					print
					added = 1
					next
				}
			}

			/^$/ && !added {
				print "'"$key"': '"$value"'"
				print
				added = 1
				next
			}

			{
				print
			}
		'
		;;
	acked-by | signed-off-by)
		local line="$key: $value"
		local header=$(cat && echo ---)

		echo -n "${header%---}" | _append_attribution "$line"
		;;
	"cherry picked from commit" | "cherry picked for")
		local line
		local header=$(cat && echo ---)
		local nb=$(countkeys "$key" <<< "$header")

		if [ $nb -gt 0 ]; then
			echo "Error: key \"$key\" already present." > /dev/stderr
			exit 1
		fi

		line="($key $value)"

		echo -n "${header%---}" | _append_attribution "$line"
		;;
	*)
		echo "Error: I don't know where to add a tag of type \"$key\"." > /dev/stderr
		exit 1
	esac
}

# get_attributions
get_attributions () {
	awk '
		tolower($1) ~ /^(acked|reviewed|signed-off)-by:$/ {
			print
		}
	'
}

# get_attribution_names
get_attribution_names () {
	get_attributions | awk '
		{
			split($0, array, FS, seps)
			print substr($0, 1 + length(seps[0]) + length(array[1]) + length(seps[1]))
		}
	'
}

# _append_attribution <attribution line>
_append_attribution () {
	local line=$1

	awk --assign line="$line" '
		BEGIN {
			added = 0
			empty_line_nb = 0
			attribseen = 0
		}

		function print_attribution(attribseen, line, before_diffstat)
		{
			if (!attribseen) {
				print ""
			}
			print line
			if (!before_diffstat) {
				print ""
			}

			added = 1
			empty_line_nb = 0
		}

		function playback_empty_lines()
		{
			for (; empty_line_nb > 0; empty_line_nb--) {
				print ""
			}
		}

		/^$/ {
			empty_line_nb++
			next
		}

		tolower($1) ~ /^[^ ]+-by:$/ {
			attribseen = 1
		}

		/^\(cherry picked from commit [[:xdigit:]]{6,})$/ {
			attribseen = 1
		}

		/^\(cherry picked for .*)$/ {
			attribseen = 1
		}

		!added && /^---$/ {
			print_attribution(attribseen, line, 1)
		}

		# from quilt, patchfns
		!added && /^(---|\*\*\*|Index:)[ \t][^ \t]|^diff -/ {
			print_attribution(attribseen, line, 0)
		}

		{
			playback_empty_lines()
			print
		}

		END {
			if (!added) {
				print_attribution(attribseen, line, 1)
			} else {
				playback_empty_lines()
			}
		}
	'
}

# insert_attributions <attribution lines>
# Add multiple attribution lines
insert_attributions () {
	local attrs=$1
	local header=$(cat && echo ---)

	if [ "$(get_attributions <<< ${header%---})" ]; then
		echo -n "${header%---}" | awk --assign attr="$1" '
			tolower($1) ~ /^[^ ]+-by:$/ {
				print attr
			}

			{
				print
			}
		'
	else
		while read attribution; do
			header=$(echo -n "${header%---}" | _append_attribution "$attribution" && echo ---)
		done <<< "$attrs"

		echo -n "${header%---}"
	fi
}
