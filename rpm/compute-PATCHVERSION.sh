#! /bin/sh

export LANG=POSIX

if ! test -d patches.kernel.org; then
	if test -e patches.kernel.org.tar.bz2; then
		tar xjf patches.kernel.org.tar.bz2
		trap 'rm -rf patches.kernel.org' EXIT
	else
		echo "Can't find patches.kernel.org" >&2
	fi
fi

source $(dirname $0)/config.sh
set -- $(echo $SRCVERSION | sed -ne 's/\([0-9]\+\).\([0-9]\+\).\([0-9]\+\)\(.*\)/\1 \2 \3 \4/p')

VERSION=$1
PATCHLEVEL=$2
SUBLEVEL=$3
EXTRAVERSION=$4

EXTRA_SYMBOLS=$(set -- $([ -e $(dirname $0)/extra-symbols ] && cat $(dirname $0)/extra-symbols) ; echo $*)

# Parse all the changes to KERNELRELEASE out of all patches and
# convert them to shell code that can be evaluated. Evaluate it.
eval "$(
    $(dirname $0)/guards $EXTRA_SYMBOLS < series.conf | grep '^patches\.kernel\.org' \
    | xargs awk '
    /^--- |^+++ / \
	{ M = match($2, /^[^\/]+\/Makefile( \t|$)/) }
    M && /^+(VERSION|PATCHLEVEL|SUBLEVEL|EXTRAVERSION)/ \
	{ print }
    ' \
    | sed -e 's,^+,,' -e 's, *= *\(.*\),="\1",'
)"
KERNELRELEASE="$VERSION.$PATCHLEVEL.$SUBLEVEL$EXTRAVERSION"

echo "$KERNELRELEASE"
