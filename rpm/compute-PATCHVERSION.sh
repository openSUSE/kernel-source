#! /bin/bash

export LANG=POSIX

path=(.)
while test $# -gt 0; do
	case "$1" in
	--patches)
		path[${#path[@]}]=$2
		shift 2
		;;
	*)
		echo "Usage $0 [--patches <dir>]" >&2
		exit 1
	esac
done
if test "${path[*]}" = "."; then
	path=(. ..)
fi


source $(dirname $0)/config.sh
parse_srcversion()
{
	local IFS=.
	set -- ${SRCVERSION%%-*}
	VERSION=$1
	PATCHLEVEL=${2:-0}
	SUBLEVEL=${3:-0}
	EXTRAVERSION=${SRCVERSION#${SRCVERSION%%-*}}
}
parse_srcversion

EXTRA_SYMBOLS=$(set -- $([ -e $(dirname $0)/extra-symbols ] && cat $(dirname $0)/extra-symbols) ; echo $*)

series=$(mktemp)
tmp_files="$series"
trap 'rm -rf $tmp_files' EXIT
warned=false
while read patch; do
	dir=${patch%/*}
	for p in "${path[@]}"; do
		if test -e "$p/$patch"; then
			echo "$p/$patch"
			continue 2
		fi
	done
	for p in "${path[@]}"; do
		if test -e "$p/$dir.tar.bz2"; then
			echo "unpacking $p/$dir.tar.bz2" >&2
			if ! $warned; then
				echo "pass --patches <directory with unpacked tarballs> to avoid this" >&2
				warned=true
			fi
			tmp_files="$tmp_files $dir"
			tar -xjf "$p/$dir.tar.bz2"
			echo "$patch"
			continue 2
		fi
	done
	echo "Can't find $patch" >&2
	exit 1
done >"$series" < <($(dirname $0)/guards $EXTRA_SYMBOLS <series.conf)

# Parse all the changes to KERNELRELEASE out of all patches and
# convert them to shell code that can be evaluated. Evaluate it.
eval "$( {
    <"$series" xargs awk '
    /^--- |^\+\+\+ / \
	{ M = match($2, /^[^\/]+\/Makefile( \t|$)/) }
    M && /^+(VERSION|PATCHLEVEL|SUBLEVEL|EXTRAVERSION)/ \
	{ print }
    ' || echo exit 1 ; } \
    | sed -e 's,^+,,' -e 's, *= *\(.*\),="\1",'
)"

echo "$VERSION.$PATCHLEVEL.$SUBLEVEL$EXTRAVERSION"
