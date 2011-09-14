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

source $(dirname $0)/config.sh
source $(dirname $0)/wd-functions.sh

have_arch_patches=false
have_defconfig_files=false
fuzz="-F0"
case "$DIST_SET" in
sles9 | sles10)
	fuzz=
esac
case "$DIST_SET" in
sles9* | sles10* | sle10* | 9.* | 10.* | 11.0)
	have_arch_patches=true
	have_defconfig_files=true
esac

usage() {
    cat <<END
SYNOPSIS: $0 [-qv] [--symbol=...] [--dir=...]
          [--combine] [--fast] [last-patch-name] [--vanilla] [--fuzz=NUM]
          [--patch-dir=PATH] [--build-dir=PATH] [--config=ARCH-FLAVOR [--kabi]]
          [--ctags] [--cscope]

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
END
    exit 1
}

# Allow to pass in default arguments via SEQUENCE_PATCH_ARGS.
set -- $SEQUENCE_PATCH_ARGS "$@"

if $have_arch_patches; then
	arch_opt="arch:"
else
	arch_opt=""
fi
options=`getopt -o qvd:F: --long quilt,no-quilt,$arch_opt,symbol:,dir:,combine,fast,vanilla,fuzz,patch-dir:,build-dir:,config:,kabi,ctags,cscope -- "$@"`

if [ $? -ne 0 ]
then
    usage
fi

eval set -- "$options"

QUIET=1
EXTRA_SYMBOLS=
QUILT=true
COMBINE=
FAST=
VANILLA=false
SP_BUILD_DIR=
CONFIG=
CONFIG_ARCH=
CONFIG_FLAVOR=
KABI=false
CTAGS=false
CSCOPE=false

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
	    COMBINE=1
	    FAST=1
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
if [ "$VANILLA" = "true" ]; then
	TAG=${TAG}-vanilla
fi
PATCH_LOG=$SCRATCH_AREA/patch-$SRCVERSION${TAG:+-$TAG}.log
LAST_LOG=$SCRATCH_AREA/last-$SRCVERSION${TAG:+-$TAG}.log

# Check series.conf.
if [ ! -r series.conf ]; then
    echo "Configuration file \`series.conf' not found"
    exit 1
fi
if [ -e scripts/check-patches ]; then
    scripts/check-patches || {
	echo "Inconsistencies found."
	echo "Please clean up series.conf and/or the patches directories!"
	read
    }
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
    PATCH_DIR=$SCRATCH_AREA/linux-$SRCVERSION${TAG:+-$TAG}{$EXT:+-}$EXT
fi

if [ -n "$SP_BUILD_DIR" ]; then
    # This allows alias (~) and variable expansion
    SP_BUILD_DIR=$(eval echo "$SP_BUILD_DIR")
else
    SP_BUILD_DIR="$PATCH_DIR"
fi

echo "Creating tree in $PATCH_DIR"

# Clean up from previous run
rm -f "$PATCH_LOG" "$LAST_LOG"
if [ -e $PATCH_DIR ]; then
    tmpdir=$(mktemp -d ${PATCH_DIR%/*}/${0##*/}.XXXXXX)
    if [ -n "$tmpdir" ]; then
	echo "Cleaning up from previous run (background)"
	mv $PATCH_DIR $tmpdir
	rm -rf $tmpdir &
    else
	echo "Cleaning up from previous run"
	rm -rf $PATCH_DIR
    fi
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
if [ -n "$LIMIT" ]; then
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
	esac
    done
    if ((n == ${#PATCHES[@]})); then
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

if [ -n "$COMBINE" ]; then
    echo "Precomputing combined patches"
    (IFS=$'\n'; echo "${PATCHES[*]}") \
    | $(dirname $0)/md5fast --source-tree "$ORIG_DIR" \
			    --temp "$SCRATCH_AREA" \
    			    --cache combined --generate
    echo $SRCVERSION > combined/srcversion
fi

if [ -n "$FAST" -a ${#PATCHES_BEFORE[@]} -gt 0 -a \
     $SRCVERSION = "$(cat combined/srcversion 2> /dev/null)" ]; then
    echo "Checking for precomputed combined patches"
    PATCHES=( $(IFS=$'\n'; echo "${PATCHES_BEFORE[*]}" \
	        | $(dirname $0)/md5fast --cache combined)
    	      "${PATCHES_AFTER[@]}" )
fi

# Helper function to restore files backed up by patch. This is
# faster than doing a --dry-run first.
restore_files() {
    local backup_dir=$1 patch_dir=$2 file wd=$PWD
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

# Create hardlinked source tree
echo "Linking from $ORIG_DIR"
cp -rld $ORIG_DIR $PATCH_DIR

echo -e "# Symbols: $SYMBOLS\n#" > $PATCH_DIR/series
SERIES_PFX=
if ! $QUILT; then
    SERIES_PFX="# "
fi

mkdir $PATCH_DIR/.pc
echo 2 > $PATCH_DIR/.pc/.version

# Patch kernel
set -- "${PATCHES[@]}"
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

    exec 5<&1  # duplicate stdin
    case $PATCH in
    *.gz)	exec < <(gzip -cd $PATCH) ;;
    *.bz2)	exec < <(bzip2 -cd $PATCH) ;;
    *)		exec < $PATCH ;;
    esac
    patch -d $PATCH_DIR --backup --prefix=$backup_dir/ -p1 -E $fuzz \
	    --no-backup-if-mismatch --force > $LAST_LOG 2>&1
    STATUS=$?
    exec 0<&5  # restore stdin
    
    if [ $STATUS -ne 0 ]; then
        restore_files $backup_dir $PATCH_DIR
    fi
    if ! $QUILT; then
	rm -rf $PATCH_DIR/.pc/
    fi
    cat $LAST_LOG >> $PATCH_LOG
    [ -z "$QUIET" ] && cat $LAST_LOG
    if [ $STATUS -ne 0 ]; then
	[ -n "$QUIET" ] && cat $LAST_LOG
	echo "Patch $PATCH failed (rolled back)."
	echo "Logfile: $PATCH_LOG"
	status=1
	break
    else
	echo "$SERIES_PFX$PATCH" >> $PATCH_DIR/series
	if $QUILT; then
	    echo "$PATCH" >> $PATCH_DIR/.pc/applied-patches
	fi
	rm -f $LAST_LOG
    fi

    shift
    if $QUILT && test "$PATCH" = "$LIMIT"; then
	break
    fi
done

if [ -n "$EXTRA_SYMBOLS" ]; then
    echo "$EXTRA_SYMBOLS" > $PATCH_DIR/extra-symbols
fi

if ! $QUILT; then
    rm $PATCH_DIR/series
fi

ln -s $PWD $PATCH_DIR/patches
ln -s patches/scripts/{refresh_patch,run_oldconfig}.sh $PATCH_DIR/
if $QUILT; then
    [ -r $HOME/.quiltrc ] && . $HOME/.quiltrc
    [ ${QUILT_PATCHES-patches} != patches ] \
        && ln -s $PWD $PATCH_DIR/${QUILT_PATCHES-patches}
fi
# If there are any remaining patches, add them to the series so
# they can be fixed up with quilt (or similar).
if [ -n "$*" ]; then
    ( IFS=$'\n' ; echo "$*" ) >> $PATCH_DIR/series
fi

echo "[ Tree: $PATCH_DIR ]"

append=
if test "$SP_BUILD_DIR" != "$PATCH_DIR"; then
    mkdir -p "$SP_BUILD_DIR"
    echo "[ Build Dir: $SP_BUILD_DIR ]"
    rm -f "$SP_BUILD_DIR/source"
    rm -f "$SP_BUILD_DIR/patches"
    ln -sf "$PATCH_DIR" "$SP_BUILD_DIR/source"
    ln -sf "source/patches" "$SP_BUILD_DIR/patches"
fi

if test -e supported.conf; then
    echo "[ Generating Module.supported ]"
    scripts/guards base external < supported.conf > "$SP_BUILD_DIR/Module.supported"
fi

if test -n "$CONFIG"; then
    if test -e "config/$CONFIG_ARCH/$CONFIG_FLAVOR"; then
	echo "[ Copying config/$CONFIG_ARCH/$CONFIG ]"
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

if $CTAGS; then
    if ctags --version > /dev/null; then
	echo "[ Generating ctags (this may take a while)]"
	make -s --no-print-directory -C "$PATCH_DIR" O="$SP_BUILD_DIR" tags
    else
	echo "[ Could not generate ctags: ctags not found ]"
    fi
fi

if $CSCOPE; then
    if cscope -V 2> /dev/null; then
	echo "[ Generating cscope db (this may take a while)]"
	make -s --no-print-directory -C "$PATCH_DIR" O="$SP_BUILD_DIR" cscope
    else
	echo "[ Could not generate cscope db: cscope not found ]"
    fi
fi

[ $# -gt 0 ] && exit $status

if ! $have_defconfig_files || test ! -e config.conf; then
    exit 0
fi

# Copy the config files that apply for this kernel.
echo "[ Copying config files ]" >> $PATCH_LOG
echo "[ Copying config files ]"
TMPFILE=$(mktemp /tmp/$(basename $0).XXXXXX)
chmod a+r $TMPFILE
CONFIGS=$(scripts/guards --list < config.conf)
for config in $CONFIGS; do
    if ! [ -e config/$config ]; then
	echo "Configuration file config/$config not found"
    fi
    name=$(basename $config)
    path=arch/$(dirname $config)/defconfig.$name
    mkdir -p $(dirname $PATCH_DIR/$path)

    chmod +x rpm/config-subst
    cat config/$config \
    | rpm/config-subst CONFIG_CFGNAME \"$name\" \
    | rpm/config-subst CONFIG_RELEASE \"0\" \
    | rpm/config-subst CONFIG_SUSE_KERNEL y \
    > $TMPFILE

    echo $path >> $PATCH_LOG
    [ -z "$QUIET" ] && echo $path
    # Make sure we don't override a hard-linked file.
    rm -f $PATCH_DIR/$path
    cp -f $TMPFILE $PATCH_DIR/$path
done
rm -f $TMPFILE
