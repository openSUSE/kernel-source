#!/bin/sh
#
# Takes clean tarball and patches it with all patches according to series.conf.
#

source $(dirname $0)/config.sh

usage() {
    echo "SYNOPSIS: $0 [-qv] [--arch=...] [--symbol=...] [--dir=...] [last-patch-name]"
    exit 1
}

# Allow to pass in default arguments via SEQUENCE_PATCH_ARGS.
set -- $SEQUENCE_PATCH_ARGS "$@"

options=`getopt -o qvd: --long quilt,arch:,symbol:,dir: -- "$@"`

if [ $? -ne 0 ]
then
    usage
fi

eval set -- "$options"

QUIET=1
EXTRA_SYMBOLS=
CLEAN=1

while true; do
    case "$1" in
    	-q)
	    QUIET=1
	    ;;
    	-v)
	    QUIET=
	    ;;
	--quilt)
	    CLEAN=
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
    echo "SCRATCH_AREA not defined (set to /var/tmp/scratch or similar)"
    exit 1
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
PATCH_DIR=$SCRATCH_AREA/linux-$VERSION
PATCH_LOG=$SCRATCH_AREA/patch-$VERSION.log
LAST_LOG=$SCRATCH_AREA/last-$VERSION.log

# Check if we can clean up backup files at the end
# (slightly faster, but requires more disk space).
free_blocks="$(df -P "$SCRATCH_AREA" \
    | awk 'NR==2 && match($4, /^[0-9]*$/) { print $4 }' 2> /dev/null)"
[ "0$free_blocks" -gt 262144 ] && enough_free_space=1

echo "Creating tree in $PATCH_DIR"

if [ ! -d $PATCH_DIR.orig ]; then
    # Check if linux-$VERSION.tar.gz is accessible.
    for file in {$SCRATCH_AREA/,,$MIRROR/,$MIRROR/testing/}linux-$VERSION.tar.{gz,bz2}; do
	if [ -r $file ]; then
	    LINUX_ORIG_TARBALL=$file
	    [ ${file:(-3)} = .gz  ] && COMPRESS_MODE=z
	    [ ${file:(-4)} = .bz2 ] && COMPRESS_MODE=j
	    break
	fi
    done
    if [ -z "$LINUX_ORIG_TARBALL" ]; then
	echo "Kernel source archive \`linux-$VERSION.tar.gz' not found," >&2
	echo "alternatively you can put an unpatched kernel tree to" >&2
	echo "$PATCH_DIR.orig." >&2
	exit 1
    fi
fi

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

if [ -z "$SYMBOLS" ]; then
    if [ -z "$ARCH_SYMBOLS" ]; then
	if [ -x arch-symbols ]; then
	    ARCH_SYMBOLS=arch-symbols
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
fi

echo "Architecture symbol(s): $SYMBOLS"
if [ -s extra-symbols ]; then
	EXTRA_SYMBOLS="$EXTRA_SYMBOLS $(cat extra-symbols)"
fi
if [ -n "$EXTRA_SYMBOLS" ]; then
    echo "Extra symbols: $EXTRA_SYMBOLS"
    SYMBOLS="$SYMBOLS $EXTRA_SYMBOLS"
fi

PATCHES=$(scripts/guards $SYMBOLS < series.conf)

# Check if patch $LIMIT exists
if [ -n "$LIMIT" ]; then
    for PATCH in $PATCHES; do
	if [ "$LIMIT" = - ]; then
	    LIMIT=$PATCH
	fi
	case $PATCH in 
	    $LIMIT|*/$LIMIT)
		LIMIT=$PATCH
		unset PATCH
		break
		;;
	esac
    done
    if [ -n "$PATCH" ]; then
	echo "No patch \`$LIMIT' found."
	exit 1
    fi
fi

# Clean up from previous run
echo "Cleaning up from previous run"
rm -f "$PATCH_LOG" "$LAST_LOG"
rm -rf $PATCH_DIR/

# Create fresh $SCRATCH_AREA/linux-$VERSION.
if [ -d $PATCH_DIR.orig ]; then
    echo "Linking from $PATCH_DIR.orig"
    cp -rld $PATCH_DIR.orig $PATCH_DIR
else
    echo "Extracting $LINUX_ORIG_TARBALL"
    tar xf$COMPRESS_MODE $LINUX_ORIG_TARBALL --directory $SCRATCH_AREA
    if [ ! -e $PATCH_DIR -a -e ${PATCH_DIR%-$VERSION} ]; then
	# Old kernels unpack into linux/ instead of linux-$VERSION/.
	mv ${PATCH_DIR%-$VERSION} $PATCH_DIR
    fi
    cp -rld $PATCH_DIR $PATCH_DIR.orig
    find $PATCH_DIR.orig -type f | xargs chmod a-w,a+r
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
	    && cp -f --parents "${restore[@]}" $patch_dir
	cd $patch_dir
	#echo "Remove: ${remove[@]}"
	[ ${#remove[@]} -ne 0 ] \
	    && rm -f "${remove[@]}"
	popd > /dev/null
    fi
}

echo -e "# Symbols: $SYMBOLS\n#" > $PATCH_DIR/series
mkdir $PATCH_DIR/.pc
echo 2 > $PATCH_DIR/.pc/.version

# Patch kernel
set -- $PATCHES
while [ $# -gt 0 ]; do
    PATCH="$1"
    if [ "$PATCH" = "$LIMIT" -a -n "$CLEAN" ]; then
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
    patch -d $PATCH_DIR --backup --prefix=$backup_dir/ -p1 -E \
	    --no-backup-if-mismatch < $PATCH > $LAST_LOG 2>&1
    STATUS=$?
    [ $STATUS -ne 0 ] \
	&& restore_files $backup_dir $PATCH_DIR
    [ -n "$CLEAN" -a -z "$enough_free_space" ] \
	&& rm -rf $PATCH_DIR/.pc/
    cat $LAST_LOG >> $PATCH_LOG
    [ -z "$QUIET" ] && cat $LAST_LOG
    if [ $STATUS -ne 0 ]; then
	[ -n "$QUIET" ] && cat $LAST_LOG
	echo "Patch $PATCH failed (rolled back)."
	echo "Logfile: $PATCH_LOG"
	status=1
	break
    else
	echo "${CLEAN:+# }$PATCH" >> $PATCH_DIR/series
	[ -z "$CLEAN" ] \
	    && echo "$PATCH" >> $PATCH_DIR/.pc/applied-patches
	rm -f $LAST_LOG
    fi

    shift
    if [ "$PATCH" = "$LIMIT" -a -z "$CLEAN" ]; then
	break
    fi
done

[ -n "$CLEAN" -a -n "$enough_free_space" ] \
    && rm -rf $PATCH_DIR/.pc/

if [ -n "$CLEAN" ]; then
    rm $PATCH_DIR/series
fi

ln -s $PWD $PATCH_DIR/patches
# If there are any remaining patches, add them to the series so
# they can be fixed up with quilt (or similar).
if [ -n "$*" ]; then
    ( IFS=$'\n' ; echo "$*" ) >> $PATCH_DIR/series
fi

rm -f $PATCH_DIR/rpm-release

[ $# -gt 0 ] && exit $status

# Old kernels don't have a config.conf.
[ -e config.conf ] || exit

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
    | rpm/config-subst CONFIG_LOCALVERSION \"-$name\" \
    | rpm/config-subst CONFIG_SUSE_KERNEL y \
    > $TMPFILE

    echo $path >> $PATCH_LOG
    [ -z "$QUIET" ] && echo $path
    # Make sure we don't override a hard-linked file.
    rm -f $PATCH_DIR/$path
    cp -f $TMPFILE $PATCH_DIR/$path
done
rm -f $TMPFILE
