#!/bin/sh

source $(dirname $0)/config.sh

PATCH_DIR=$SCRATCH_AREA/linux-$VERSION
PATCH_LOG=$SCRATCH_AREA/patch-$VERSION.log
LAST_LOG=$SCRATCH_AREA/last-$VERSION.log
QUIET=1

while [ $# -gt 0 ]; do
    case $1 in
    	(-q)
	    QUIET=1
	    ;;
    	(-v)
	    unset QUIET
	    ;;
	([^-]*)
	    [ -n "$LIMIT" ] && break
	    LIMIT=$1
	    ;;
	(*)
	    break
	    ;;
    esac
    shift
done
if [ $# -gt 0 ]; then
    echo "SYNOPSIS: $0 [-v] [last-patch-name]"
    exit 1
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
    echo "Please export SCRATCH_AREA=/tmp/kscratch (example)"
    echo "creating a temporary scratch area does not work yet"
    exit 1
fi
#if [[ "$SCRATCH_AREA" != /* ]]; then
#    SCRATCH_AREA="$PWD/$SCRATCH_AREA"
#fi
if [ ! -d "$SCRATCH_AREA" ]; then
    if ! mkdir -p $SCRATCH_AREA; then
	echo "creating scratch dir $SCRATCH_AREA failed"
	exit 1
    fi
fi

echo "Creating tree in $PATCH_DIR"

if [ ! -d $PATCH_DIR.orig ]; then
    # Check if linux-$VERSION.tar.gz is accessible.
    if [ -z "$LINUX_ORIG_TARBALL" ]; then
	if [ -r $SCRATCH_AREA/linux-$VERSION.tar.gz ]; then
	    LINUX_ORIG_TARBALL=$SCRATCH_AREA/linux-$VERSION.tar.gz
            COMPRESS_MODE=z
	elif [ -r $SCRATCH_AREA/linux-$VERSION.tar.bz2 ]; then
	    LINUX_ORIG_TARBALL=$SCRATCH_AREA/linux-$VERSION.tar.bz2
            COMPRESS_MODE=j
	elif [ -r linux-$VERSION.tar.gz ]; then
	    LINUX_ORIG_TARBALL=linux-$VERSION.tar.gz
            COMPRESS_MODE=z
        elif [ -r linux-$VERSION.tar.bz2 ]; then
	    LINUX_ORIG_TARBALL=linux-$VERSION.tar.bz2
            COMPRESS_MODE=j
	elif [ -r $MIRROR/linux-$VERSION.tar.gz ]; then
	    LINUX_ORIG_TARBALL=$MIRROR/linux-$VERSION.tar.gz
            COMPRESS_MODE=z
	elif [ -r $MIRROR/linux-$VERSION.tar.bz2 ]; then
	    LINUX_ORIG_TARBALL=$MIRROR/linux-$VERSION.tar.bz2
            COMPRESS_MODE=j
	else
	    LINUX_ORIG_TARBALL=linux-$VERSION.tar.gz
	fi
    fi
    if [ ! -r "$LINUX_ORIG_TARBALL" ]; then
	echo "Kernel source archive \`$LINUX_ORIG_TARBALL' not found," >&2
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
if [ -e scripts/check-conf ]; then
    scripts/check-conf || {
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
	EXTRA_SYMBOLS=$(cat extra-symbols)
	echo "Extra symbols: $EXTRA_SYMBOLS"
	SYMBOLS="$SYMBOLS $EXTRA_SYMBOLS"
fi

PATCHES=$(scripts/guards $SYMBOLS < series.conf)

# Check if patch $LIMIT exists
if [ -n "$LIMIT" ]; then
    for PATCH in $PATCHES; do
	case $PATCH in 
	    (*/$LIMIT)
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
echo -e "# Symbols: $SYMBOLS\n#" > $SCRATCH_AREA/series

# Create fresh $SCRATCH_AREA/linux-$VERSION.
if [ -d $PATCH_DIR.orig ]; then
    echo "Linking from $PATCH_DIR.orig"
    cp -rld $PATCH_DIR.orig $PATCH_DIR
else
    echo "Extracting $LINUX_ORIG_TARBALL"
    tar xf$COMPRESS_MODE $LINUX_ORIG_TARBALL --directory $SCRATCH_AREA
    cp -rld $PATCH_DIR $PATCH_DIR.orig
fi

# Patch kernel
for PATCH in $PATCHES; do
    if [ "$PATCH" = "$LIMIT" ]; then
	STEP_BY_STEP=1
	echo "*** Stopping before $PATCH ***"
    fi
    if [ -n "$STEP_BY_STEP" ]; then
	while true; do
	    echo -n "Continue (y/n/a)?"
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
	echo "*** Patch $PATCH not found ***"
	exit 1
    fi
    echo "[ $PATCH ]"
    echo "[ $PATCH ]" >> $PATCH_LOG
    echo $PATCH >> $SCRATCH_AREA/series
    patch -d $PATCH_DIR --no-backup-if-mismatch -p1 \
    	< $PATCH > $LAST_LOG 2>&1
    STATUS=$?
    cat $LAST_LOG >> $PATCH_LOG
    [ -z "$QUIET" ] && cat $LAST_LOG
    if [ $STATUS -ne 0 ]; then
	[ -n "$QUIET" ] && cat $LAST_LOG
	echo "*** Patch $PATCH failed ***" >&2
	exit 1
    else
	rm -f $LAST_LOG
    fi
done


# config_subst makes sure that CONFIG_CFGNAME and CONFIG_RELEASE are
# set correctly.

config_subst()
{
    local name=$1 release=$2
    awk '
	function print_name(force)
	{
	    if (!done_name || force)
		printf "CONFIG_CFGNAME=\"%s\"\n", "'"$name"'"
	    done_name=1
	}
	function print_release(force)
	{
	    if (!done_release || force)
		printf "CONFIG_RELEASE=%d\n", '"$release"'
	    done_release=1
	}

	/\<CONFIG_CFGNAME\>/	{ print_name(1) ; next }
	/\<CONFIG_RELEASE\>/	{ print_release(1) ; next }
				{ print }
	END			{ print_name(0) ; print_release(0) }
    '
}

# Copy the config files that apply for this kernel.
echo "[ Copying config files ]" >> $PATCH_LOG
echo "[ Copying config files ]"
CONFIGS=$(scripts/guards $SYMBOLS < config.conf)
for config in $CONFIGS; do
	if ! [ -e config/$config ]; then
		echo "*** Configuration file config/$config not found ***"
	fi
	name=$(basename $config)
	path=arch/$(dirname $config)/defconfig.$name
	mkdir -p $(dirname $PATCH_DIR/$path)
	if [ "${config/*\//}" = "default" ]; then
		echo ${path%.default} >> $PATCH_LOG
		[ -z "$QUIET" ] && echo ${path%.default}

		config_subst $name 0 \
			< config/$config \
			> $PATCH_DIR/${path%.default}
	fi
	echo $path >> $PATCH_LOG
	[ -z "$QUIET" ] && echo $path

	config_subst $name 0 \
		< config/$config \
		> $PATCH_DIR/$path
done

