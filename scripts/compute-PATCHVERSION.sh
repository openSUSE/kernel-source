#! /bin/sh

export LANG=POSIX

source $(dirname $0)/config.sh
set -- $(IFS=.; echo $SRCVERSION)

VERSION=$1
PATCHLEVEL=$2
SUBLEVEL=$3
EXTRAVERSION=

EXTRA_SYMBOLS=$([ -e extra-symbols ] && cat extra-symbols)

# Parse all the changes to KERNELRELEASE out of all patches and
# convert them to shell code that can be evaluated. Evaluate it.
eval "$(
    scripts/guards $EXTRA_SYMBOLS < series.conf \
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
