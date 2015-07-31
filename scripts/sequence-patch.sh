#! /bin/bash

#############################################################################
# Copyright (c) 2003-2005,2007-2009 Novell, Inc.
# All Rights Reserved.
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of version 2 of the GNU General Public License as
# published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.   See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, contact Novell, Inc.
#
# To contact Novell about this file by physical or electronic mail,
# you may find current contact information at www.novell.com
#############################################################################

source $(dirname $0)/../rpm/config.sh
source $(dirname $0)/wd-functions.sh

set -o pipefail

have_arch_patches=false
fuzz="-F0"
case "$IBS_PROJECT" in
SUSE:SLE-9*)
	fuzz=
	have_arch_patches=true
esac

usage() {
    cat <<END
SYNOPSIS: $0 [-qv] [--symbol=...] [--dir=...]
          [--fast] [last-patch-name] [--vanilla] [--fuzz=NUM]
          [--patch-dir=PATH] [--build-dir=PATH] [--config=ARCH-FLAVOR [--kabi]]
          [--ctags] [--cscope] [--no-xen] [--skip-reverse]

  The --build-dir option supports internal shell aliases, like ~, and variable
  expansion when the variables are properly escaped.  Environment variables
  and the following list of internal variables are permitted:
  \$PATCH_DIR:		The expanded source tree
  \$SRCVERSION:		The current linux source tarball version
  \$TAG:			The current tag or branch of this repo
  \$EXT:			A string expanded from current \$EXTRA_SYMBOLS
  With --config=ARCH-FLAVOR, these have values. Otherwise they are empty.
  \$CONFIG:		The current ARCH-FLAVOR.
  \$CONFIG_ARCH:		The current ARCH.
  \$CONFIG_FLAVOR:	The current FLAVOR.

  The --no-quilt option will still create quilt-style backups for each
  file that is modified but the backups will be removed if the patch
  is successful. This can be fast because the new files may be created
  and removed before writeback occurs so they only exist in memory. A
  failed patch will be rolled back and the caller will be able to diagnose it.

  The --fast option will concatenate all the patches to be applied and
  call patch just once. This is even faster than --no-quilt but if any
  of the component patches fail to apply the tree will not be rolled
  back.

  When used with last-patch-name or --no-xen, both --fast and --no-quilt
  will set up a quilt environment for the remaining patches.
END
    exit 1
}

apply_fast_patches() {
    echo "[ Fast-applying ${#PATCHES_BEFORE[@]} patches. ${#PATCHES_AFTER[@]} remain. ]"
    LAST_LOG=$(cat "${PATCHES_BEFORE[@]}" | \
        patch -d $PATCH_DIR -p1 -E $fuzz --force --no-backup-if-mismatch \
		-s 2>&1)
    STATUS=$?

    if [ $STATUS -ne 0 ]; then
        echo "$LAST_LOG" >> $PATCH_LOG
        [ -n "$QUIET" ] && echo "$LAST_LOG"
        echo "All-in-one patch failed (not rolled back)."
        echo "Logfile: $PATCH_LOG"
        status=1
    fi

    PATCHES=( ${PATCHES_AFTER[@]} )
}
SKIPPED_PATCHES=

# Patch kernel normally
apply_patches() {
    set -- "${PATCHES[@]}"
    n=0
    while [ $# -gt 0 ]; do
        PATCH="$1"
        if ! $QUILT && test "$PATCH" = "$LIMIT"; then
            STEP_BY_STEP=1
            echo "Stopping before $PATCH"
        fi
        if [ -n "$STEP_BY_STEP" ]; then
            while true; do
                echo -n "Continue ([y]es/[n]o/yes to [a]ll)?"
                read YESNO
                case $YESNO in
                    ([yYjJsS])
                        break
                        ;;
                    ([nN])
                        break 2	# break out of outer loop
                        ;;
                    ([aA])
                        unset STEP_BY_STEP
                        break
                        ;;
                esac
            done
        fi

        if [ ! -r "$PATCH" ]; then
            echo "Patch $PATCH not found."
            status=1
            break
        fi
        echo "[ $PATCH ]"
        echo "[ $PATCH ]" >> $PATCH_LOG
        backup_dir=$PATCH_DIR/.pc/$PATCH

        LAST_LOG=$(patch -d $PATCH_DIR --backup --prefix=$backup_dir/ -p1 -E $fuzz \
                --no-backup-if-mismatch --force < $PATCH 2>&1)
        STATUS=$?

        if [ $STATUS -ne 0 ]; then
            restore_files $backup_dir $PATCH_DIR

	    if $SKIP_REVERSE; then
		patch -R -d $PATCH_DIR -p1 -E $fuzz --force --dry-run \
			< $PATCH > /dev/null 2>&1
		ST=$?
		if [ $ST -eq 0 ]; then
			LAST_LOG="[ skipped: can be reverse-applied ]"
			[ -n "$QUIET" ] && echo "$LAST_LOG"
			STATUS=0
			SKIPPED_PATCHES="$SKIPPED_PATCHES $PATCH"
			PATCH="# $PATCH"
			remove_rejects $backup_dir $PATCH_DIR
		fi
	    fi

	    # Backup directory is no longer needed
	    rm -rf $backup_dir
	else
	    if $QUILT; then
		echo "$PATCH" >> $PATCH_DIR/.pc/applied-patches
	    fi
        fi

        if ! $QUILT; then
            rm -rf $PATCH_DIR/.pc/
        fi
        echo "$LAST_LOG" >> $PATCH_LOG
        [ -z "$QUIET" ] && echo "$LAST_LOG"
        if [ $STATUS -ne 0 ]; then
            [ -n "$QUIET" ] && echo "$LAST_LOG"
            echo "Patch $PATCH failed (rolled back)."
            echo "Logfile: $PATCH_LOG"
            status=1
            break
        else
            echo "$SERIES_PFX$PATCH" >> $PATCH_DIR/series
        fi

        shift
	if $QUILT; then
		unset PATCHES[$n]
	fi
	let n++
        if $QUILT && test "$PATCH" = "$LIMIT"; then
            break
        fi
    done
}

show_skipped() {
    if [ -n "$SKIPPED_PATCHES" ]; then
	echo "The following patches were skipped and can be removed from series.conf:"
	for p in $SKIPPED_PATCHES; do
	    echo "$p"
	done
    fi
}

# Allow to pass in default arguments via SEQUENCE_PATCH_ARGS.
set -- $SEQUENCE_PATCH_ARGS "$@"

if $have_arch_patches; then
	arch_opt="arch:"
else
	arch_opt=""
fi
options=`getopt -o qvd:F: --long quilt,no-quilt,$arch_opt,symbol:,dir:,combine,fast,vanilla,fuzz,patch-dir:,build-dir:,config:,kabi,ctags,cscope,no-xen,skip-reverse -- "$@"`

if [ $? -ne 0 ]
then
    usage
fi

eval set -- "$options"

QUIET=1
EXTRA_SYMBOLS=
QUILT=true
FAST=
VANILLA=false
SP_BUILD_DIR=
CONFIG=
CONFIG_ARCH=
CONFIG_FLAVOR=
KABI=false
CTAGS=false
CSCOPE=false
SKIP_XEN=false
SKIP_REVERSE=false

while true; do
    case "$1" in
    	-q)
	    QUIET=1
	    ;;
    	-v)
	    QUIET=
	    ;;
	--quilt)
	    QUILT=true
	    ;;
	--no-quilt)
	    QUILT=false
	    ;;
	--combine)
	    # ignored
	    ;;
       	--fast)
	    FAST=1
	    ;;
	--arch)
	    export PATCH_ARCH=$2
	    shift
	    ;;
	--symbol)
	    EXTRA_SYMBOLS="$EXTRA_SYMBOLS $2"
	    shift
	    ;;
	-d|--dir)
	    SCRATCH_AREA=$2
	    shift
	    ;;
	--vanilla)
	    VANILLA=true
	    ;;
	-F|--fuzz)
	    fuzz="-F$2"
	    shift
	    ;;
        --patch-dir)
            PATCH_DIR=$2
            shift
            ;;
	--build-dir)
	    SP_BUILD_DIR="$2"
	    shift
	    ;;
	--config)
	    CONFIG="$2"
	    shift
	    ;;
	--kabi)
	    KABI=true
	    ;;
	--ctags)
	    CTAGS=true
	    ;;
	--cscope)
	    CSCOPE=true
	    ;;
	--no-xen)
	    SKIP_XEN=true
	    ;;
	--skip-reverse)
	    SKIP_REVERSE=true
	    ;;
	--)
	    shift
	    break ;;
	*)
	    usage ;;
    esac
    shift
done

unset LIMIT
if [ $# -ge 1 ]; then
    LIMIT=$1
    shift
fi

if test -z "$CONFIG"; then
	if test "$VANILLA_ONLY" = 1 || $VANILLA; then
		CONFIG=$(uname -m)-vanilla
	else
		machine=$(uname -m)
		case "$machine" in
		i?86)
			machine=i386
		esac
		if test -e "config/$machine/smp"; then
			CONFIG=$machine-smp
		elif test -e "config/$machine/pae"; then
			CONFIG=$machine-pae
		elif test -e "config/$machine/default"; then
			CONFIG=$machine-default
		elif test -e "config/$machine/rt"; then
			CONFIG=$machine-rt
		else
			echo "Cannot determine default config for arch $machine"
		fi
	fi
fi

if test -n "$CONFIG"; then
	CONFIG_ARCH=${CONFIG%%-*}
	CONFIG_FLAVOR=${CONFIG##*-}
	if [ "$CONFIG" = "$CONFIG_ARCH" -o "$CONFIG" = "$CONFIG_FLAVOR" -o \
			-z "$CONFIG_ARCH" -o -z "$CONFIG_FLAVOR" ]; then
		echo "Invalid config spec: --config=ARCH-FLAVOR is expected."
		usage
	fi
fi

if [ $# -ne 0 ]; then
    usage
fi

if ! scripts/guards --prefix=config $(scripts/arch-symbols --list) < config.conf | \
     egrep -q '/(xen|ec2|pv)$'; then
     echo "*** Xen configs are disabled; Skipping Xen patches." >&2

     SKIP_XEN=true
fi

# Some patches require patch 2.5.4. Abort with older versions.
PATCH_VERSION=$(patch -v | sed -e '/^patch/!d' -e 's/patch //')
case $PATCH_VERSION in
    ([01].*|2.[1-4].*|2.5.[1-3])  # (check if < 2.5.4)
	echo "patch version $PATCH_VERSION found; " \
	     "a version >= 2.5.4 required." >&2
	exit 1
    ;;
esac

# Check SCRATCH_AREA.
if [ -z "$SCRATCH_AREA" ]; then
    echo "SCRATCH_AREA not defined (defaulting to \"tmp\")"
    SCRATCH_AREA=tmp
fi
if [ ! -d "$SCRATCH_AREA" ]; then
    if ! mkdir -p $SCRATCH_AREA; then
	echo "creating scratch dir $SCRATCH_AREA failed"
	exit 1
    fi
fi

[ "${SCRATCH_AREA:0:1}" != "/" ] \
    && SCRATCH_AREA="$PWD/$SCRATCH_AREA"

TMPDIR=$SCRATCH_AREA
export TMPDIR
ORIG_DIR=$SCRATCH_AREA/linux-$SRCVERSION.orig
TAG=$(get_branch_name)
TAG=${TAG//\//_}
if $VANILLA; then
	TAG=${TAG}-vanilla
fi
PATCH_LOG=$SCRATCH_AREA/patch-$SRCVERSION${TAG:+-$TAG}.log

# Check series.conf.
if [ ! -r series.conf ]; then
    echo "Configuration file \`series.conf' not found"
    exit 1
fi
if $have_arch_patches; then
    if [ -z "$ARCH_SYMBOLS" ]; then
        if [ -x ./arch-symbols ]; then
            ARCH_SYMBOLS=./arch-symbols
        elif [ -x scripts/arch-symbols ]; then
            ARCH_SYMBOLS=scripts/arch-symbols
        else
            echo "Cannot locate \`arch-symbols' script (export ARCH_SYMBOLS)"
            exit 1
        fi
    else
        if [ ! -x "$ARCH_SYMBOLS" ]; then
            echo "Cannot execute \`arch-symbols' script"
            exit 1
        fi
    fi
    SYMBOLS=$($ARCH_SYMBOLS)
    if [ -z "$SYMBOLS" ]; then
        echo "Unsupported architecture \`$ARCH'" >&2
        exit 1
    fi
echo "Architecture symbol(s): $SYMBOLS"
fi

if [ -s extra-symbols ]; then
	EXTRA_SYMBOLS="$EXTRA_SYMBOLS $(cat extra-symbols)"
fi
if [ -n "$EXTRA_SYMBOLS" ]; then
    EXTRA_SYMBOLS=${EXTRA_SYMBOLS# }
    echo "Extra symbols: $EXTRA_SYMBOLS"
    SYMBOLS="$SYMBOLS $EXTRA_SYMBOLS"
fi

EXT=${EXTRA_SYMBOLS// /-}
EXT=${EXT//\//}

if test -z "$PATCH_DIR"; then
    PATCH_DIR=$SCRATCH_AREA/linux-$SRCVERSION${TAG:+-$TAG}${EXT:+-}$EXT
fi

if [ -n "$SP_BUILD_DIR" ]; then
    # This allows alias (~) and variable expansion
    SP_BUILD_DIR=$(eval echo "$SP_BUILD_DIR")
else
    SP_BUILD_DIR="$PATCH_DIR"
fi

echo "Creating tree in $PATCH_DIR"

# Clean up from previous run
rm -f "$PATCH_LOG"
if [ -e $PATCH_DIR ]; then
    echo "Cleaning up from previous run"
    rm -rf $PATCH_DIR
fi

# Create fresh $SCRATCH_AREA/linux-$SRCVERSION.
if ! [ -d $ORIG_DIR ]; then
    unpack_tarball "$SRCVERSION" "$ORIG_DIR"
    find $ORIG_DIR -type f | xargs chmod a-w,a+r
fi

if $VANILLA; then
	PATCHES=( $(scripts/guards $SYMBOLS < series.conf | egrep '^patches\.(kernel\.org|rpmify)/') )
else
	PATCHES=( $(scripts/guards $SYMBOLS < series.conf) )
fi

# Check if patch $LIMIT exists
if [ -n "$LIMIT" ] || $SKIP_XEN; then
    for ((n=0; n<${#PATCHES[@]}; n++)); do
	if [ "$LIMIT" = - ]; then
	    LIMIT=${PATCHES[n]}
	    break
	fi
	case "${PATCHES[n]}" in
	$LIMIT|*/$LIMIT)
	    LIMIT=${PATCHES[n]}
	    break
	    ;;
	patches.xen/*)
            if $SKIP_XEN; then
                LIMIT=${PATCHES[n-1]}
                break
            fi
            ;;
	esac
    done
    if [ -n "$LIMIT" ] && ((n == ${#PATCHES[@]})); then
	echo "No patch \`$LIMIT' found."
	exit 1
    fi
    PATCHES_BEFORE=()
    for ((m=0; m<n; m++)); do
	PATCHES_BEFORE[m]=${PATCHES[m]}
    done
    PATCHES_AFTER=()
    for ((m=n; m<${#PATCHES[@]}; m++)); do
	PATCHES_AFTER[m-n]=${PATCHES[m]}
    done
else
    PATCHES_BEFORE=( "${PATCHES[@]}" )
    PATCHES_AFTER=()
fi

# Helper function to restore files backed up by patch. This is
# faster than doing a --dry-run first.
restore_files() {
    local backup_dir=$1 patch_dir=$2 file
    local -a remove restore
 
    if [ -d $backup_dir ]; then
	pushd $backup_dir > /dev/null
	for file in $(find . -type f) ; do
	    if [ -s "$file" ]; then
		restore[${#restore[@]}]="$file"
	    else
		remove[${#remove[@]}]="$file"
	    fi
	done
	#echo "Restore: ${restore[@]}"
	[ ${#restore[@]} -ne 0 ] \
	    && printf "%s\n" "${restore[@]}" \
		| xargs cp -f --parents --target $patch_dir
	cd $patch_dir
	#echo "Remove: ${remove[@]}"
	[ ${#remove[@]} -ne 0 ] \
	    && printf "%s\n" "${remove[@]}" | xargs rm -f
	popd > /dev/null
    fi
}

# Helper function to remove stray .rej files.
remove_rejects() {
    local backup_dir=$1 patch_dir=$2 file
    local -a remove

    if [ -d $backup_dir ]; then
	pushd $backup_dir > /dev/null
	for file in $(find . -type f) ; do
	    if [ -f "$patch_dir/$file.rej" ]; then
		remove[${#remove[@]}]="$file.rej"
	    fi
	done
	cd $patch_dir
	#echo "Remove rejects: ${remove[@]}"
	[ ${#remove[@]} -ne 0 ] \
	    && printf "%s\n" "${remove[@]}" | xargs rm -f
	popd > /dev/null
    fi
}

# Create hardlinked source tree
echo "Linking from $ORIG_DIR"
cp -rld $ORIG_DIR $PATCH_DIR
# create a relative symlink
ln -snf ${PATCH_DIR#$SCRATCH_AREA/} $SCRATCH_AREA/current

echo -e "# Symbols: $SYMBOLS\n#" > $PATCH_DIR/series
SERIES_PFX=
if ! $QUILT; then
    SERIES_PFX="# "
fi

mkdir $PATCH_DIR/.pc
echo 2 > $PATCH_DIR/.pc/.version

if [ -z "$FAST" ]; then
    apply_patches
else
    apply_fast_patches
fi

if [ -n "$EXTRA_SYMBOLS" ]; then
    echo "$EXTRA_SYMBOLS" > $PATCH_DIR/extra-symbols
fi

if ! $QUILT; then
    rm $PATCH_DIR/series
fi

ln -s $PWD $PATCH_DIR/patches
ln -s patches/scripts/{refresh_patch,run_oldconfig}.sh $PATCH_DIR/
if $VANILLA; then
	touch "$PATCH_DIR/.is_vanilla"
fi
if $QUILT; then
    [ -r $HOME/.quiltrc ] && . $HOME/.quiltrc
    [ ${QUILT_PATCHES-patches} != patches ] \
        && ln -s $PWD $PATCH_DIR/${QUILT_PATCHES-patches}
fi
echo "[ Tree: $PATCH_DIR ]"

if test "$SP_BUILD_DIR" != "$PATCH_DIR"; then
    mkdir -p "$SP_BUILD_DIR"
    echo "[ Build Dir: $SP_BUILD_DIR ]"
    rm -f "$SP_BUILD_DIR/source"
    rm -f "$SP_BUILD_DIR/patches"
    ln -sf "$PATCH_DIR" "$SP_BUILD_DIR/source"
    ln -sf "source/patches" "$SP_BUILD_DIR/patches"
fi

# If there are any remaining patches, add them to the series so
# they can be fixed up with quilt (or similar).
if [ -n "${PATCHES[*]}" ]; then
    ( IFS=$'\n' ; echo "${PATCHES[*]}" ) >> $PATCH_DIR/series
fi
show_skipped
if test "0$status" -ne 0; then
    exit $status
fi

if test -e supported.conf; then
    echo "[ Generating Module.supported ]"
    scripts/guards base external < supported.conf > "$SP_BUILD_DIR/Module.supported"
fi

if test -n "$CONFIG"; then
    if test -e "config/$CONFIG_ARCH/$CONFIG_FLAVOR"; then
	echo "[ Copying config/$CONFIG_ARCH/$CONFIG_FLAVOR ]"
	cp -a "config/$CONFIG_ARCH/$CONFIG_FLAVOR" "$SP_BUILD_DIR/.config"
    else
	echo "[ Config $CONFIG does not exist. ]"
    fi

    if $KABI; then
	if [ ! -x rpm/modversions ]; then
	    echo "[ This branch does not support the modversions kABI mechanism. Skipping. ]"
	elif [ -e "kabi/$CONFIG_ARCH/symtypes-$CONFIG_FLAVOR" ]; then
	    echo "[ Expanding kABI references for $CONFIG ]"
	    rpm/modversions --unpack "$SP_BUILD_DIR" < \
		"kabi/$CONFIG_ARCH/symtypes-$CONFIG_FLAVOR"
	else
	    echo "[ No kABI references for $CONFIG ]"
	fi
    fi
fi

# Some archs we use for the config do not exist or have a different name in the
# kernl source tree
case $CONFIG_ARCH in
	s390x) TAGS_ARCH=s390 ;;
	ppc64|ppc64le) TAGS_ARCH=powerpc ;;
	*) TAGS_ARCH=$CONFIG_ARCH ;;
esac
if $CTAGS; then
    if ctags --version > /dev/null; then
	echo "[ Generating ctags (this may take a while)]"
	ARCH=$TAGS_ARCH make -s --no-print-directory -C "$PATCH_DIR" O="$SP_BUILD_DIR" tags
    else
	echo "[ Could not generate ctags: ctags not found ]"
    fi
fi

if $CSCOPE; then
    if cscope -V 2> /dev/null; then
	echo "[ Generating cscope db (this may take a while)]"
	ARCH=$TAGS_ARCH make -s --no-print-directory -C "$PATCH_DIR" O="$SP_BUILD_DIR" cscope
    else
	echo "[ Could not generate cscope db: cscope not found ]"
    fi
fi
