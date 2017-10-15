#!/bin/bash -e

# Apply the next patch in the quilt queue while cleaning and renaming it.
# Useful when importing patches into SUSE's kernel-source.git.


progname=$(basename "$0")
libdir=$(dirname "$(readlink -f "$0")")
prefix=
number="[[:digit:]]+-"
opt_commit=
opt_ref=

usage () {
	echo "Usage: $progname [options] <dst \"patches.xxx\" dir>"
	echo ""
	echo "Options:"
	echo "    -p, --prefix=<prefix>       Add a prefix to the patch file name."
	echo "    -n, --number                Keep the number prefix in the patch file name."
	echo "    -h, --help                  Print this help"
	echo "Options passed to clean_header.sh:"
	echo "    -c, --commit=<refspec>      Upstream commit id used to tag the patch file."
	echo "    -r, --reference=<bsc>       bsc or fate number used to tag the patch file."
	echo "    -R, --soft-reference=<bsc>  bsc or fate number used to tag the patch file"
	echo "                                if no other reference is found."
	echo "    -s, --skip=<domain>         Skip adding Acked-by tag if there is already an"
	echo "                                attribution line with an email from this domain."
	echo "                                (Can be used multiple times.)"
	echo ""
}

tempfiles=
clean_tempfiles () {
	local file

	echo "$tempfiles" | while read -r file; do
		if [ -n "$file" -a -f "$file" ]; then
			rm "$file"
		fi
	done
}
trap 'clean_tempfiles' EXIT


result=$(getopt -o p:nc:r:R:s:h --long prefix:,number,commit:,reference:,soft-reference:,skip:,help -n "$progname" -- "$@")

if [ $? != 0 ]; then
	echo "Error: getopt error" >&2
	exit 1
fi

eval set -- "$result"

while true ; do
        case "$1" in
                -p|--prefix)
					prefix="${2%-}-"
					shift
					;;
                -n|--number)
					number=
					;;
                -c|--commit)
					opt_commit=$2
					shift
					;;
                -r|--reference)
					opt_ref=$2
					shift
					;;
                -R|--soft-reference)
					opt_soft=$2
					shift
					;;
                -s|--skip)
					opts_skip+="-s"
					opts_skip+=($2)
					shift
					;;
                -h|--help)
					usage
					exit 0
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

if [ -z "$1" ]; then
	echo "Error: too few arguments" > /dev/stderr
	usage > /dev/stderr
	exit 1
fi

patch_dir=$1
shift
if [ ! -d patches/"$patch_dir" ]; then
	echo "Error: patch directory \"$patch_dir\" does not exist" > /dev/stderr
	exit 1
fi

if [ -n "$1" ]; then
	echo "Error: too many arguments" > /dev/stderr
	usage > /dev/stderr
	exit 1
fi

if patch_file=$(QUILT_PATCHES_PREFIX=1 quilt next); then
	patch_orig=$(mktemp --tmpdir ksapply-patch_orig.XXXXXXXXXX)
	tempfiles+=$patch_orig$'\n'
	cat "$patch_file" > "$patch_orig"
	if quilt push; then
		:
	else
		exit $?
	fi

	./refresh_patch.sh
	patch_new=$(mktemp --tmpdir ksapply-patch_new.XXXXXXXXXX)
	tempfiles+=$patch_new$'\n'
	cat "$patch_file" > "$patch_new"
	if ! "$libdir"/clean_header.sh -c "$opt_commit" -r "$opt_ref" -R "$opt_soft" "${opts_skip[@]}" "$patch_new"; then
		quilt pop
		cat "$patch_orig" > "$patch_file"
		exit 1
	fi
	cat "$patch_new" | awk -f "$libdir"/patch_header.awk | quilt header -r

	newname=$(quilt top | sed -r "s/^(patches\/)?($number)?/$prefix/")
	if ! quilt rename "$patch_dir/$newname"; then
		quilt pop
		cat "$patch_orig" > "$patch_file"
		exit 1
	fi
else
	exit $?
fi
