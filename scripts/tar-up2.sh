#!/bin/sh
# $Version$

source $(dirname $0)/config.sh
export LANG=POSIX

while [ $# -gt 0 ]; do
    case $1 in
	--arch=*)
	    export PATCH_ARCH="${1#--arch=}"
	    ;;
	--arch)
	    export PATCH_ARCH="$2"
	    shift
	    ;;
	*)
	    break
	    ;;
    esac
    shift
done
if [ $# -gt 0 ]; then
    echo "SYNOPSIS: $0 [--arch=...]"
    exit 1
fi

SRC_FILE=linux-$VERSION.tar.bz2

if [ -e scripts/check-conf ]; then
    scripts/check-conf || {
	echo "Inconsistencies found."
	echo "Please clean up series.conf and/or the patches directories!"
	exit
    }
fi

SYMBOLS=$(scripts/arch-symbols)
echo "Architecture symbol(s): $SYMBOLS"
if [ -s extra-symbols ]; then
	EXTRA_SYMBOLS="$EXTRA_SYMBOLS $(cat extra-symbols)"
fi
if [ -n "$EXTRA_SYMBOLS" ]; then
    echo "Extra symbols: $EXTRA_SYMBOLS"
    SYMBOLS="$SYMBOLS $EXTRA_SYMBOLS"
fi

[ -z "$PATCH_ARCH" ] && PATCH_ARCH="$(uname -m)"
case "$PATCH_ARCH" in
    (i?86)	PATCH_ARCH=i386 ;;
    (sun4u)	PATCH_ARCH=sparc64 ;;
    (arm*|sa110) PATCH_ARCH=arm ;;
    (s390x)	PATCH_ARCH=s390 ;;
    (parisc64)	PATCH_ARCH=parisc ;;
esac

BUILD_DIR="$PATCH_ARCH"

rm -rf $BUILD_DIR
mkdir -p $BUILD_DIR

#echo "Copying various files..."
cp -pv	kernel-source-26.changes \
	series.conf config.conf scripts/merge-headers \
	rpm/config_subst.sh rpm/running-kernel.init.in \
	rpm/functions.sh rpm/post.sh rpm/postun.sh \
	rpm/trigger-script.sh.in \
	scripts/guards scripts/arch-symbols $BUILD_DIR

[ -e skip-build ]    && cp -pv skip-build    $BUILD_DIR 
[ -e extra-symbols ] && cp -pv extra-symbols $BUILD_DIR

configs=( $(scripts/guards --prefix config $SYMBOLS < config.conf) )
# Filter out config/$ARCH/um (User Mode Linux): We do not pre-configure
# UML kernels.
um_config="$(IFS=$'\n'
	     echo "${configs[*]}" \
	     | grep '/um$')"
if [ -n "$um_config" ]; then
    configs=( $(IFS=$'\n'
    		echo "${configs[*]}" \
		| grep -v '/um$') )
fi

for config in ${configs[@]} $um_config; do
    cfgname=${config##*/}
    echo "kernel-$cfgname-26.spec"
    cat rpm/kernel-binary-26.spec.in \
    | sed -e "s:@NAME@:kernel-$cfgname-26:g" \
    	  -e "s:@ARCH@:$PATCH_ARCH:g" \
	  -e "s:@CFGNAME@:$cfgname:g" \
    | m4 > $BUILD_DIR/kernel-$cfgname-26.spec
    cat kernel-source-26.changes kernel-binary-26.changes \
	> $BUILD_DIR/kernel-$cfgname-26.changes
done

# The pre-configured kernel source package
if [ ${#configs[@]} -ne 0 ]; then
    cfgnames="${configs[@]##*/}"
    echo "kernel-source-26.spec"
    cat rpm/kernel-source-26.spec.in \
    | sed -e "s:@NAME@:kernel-source-26:g" \
	  -e "s:@ARCH@:$PATCH_ARCH:g" \
	  -e "s:@CFGNAMES@:$cfgnames:g" \
    | m4 > $BUILD_DIR/kernel-source-26.spec
fi

# The unconfigured kernel source package: Source for User Mode Linux, and
# for any km_* packages that absolutely think they need kernel sources
# installed.
echo "kernel-bare-26.spec"
cat rpm/kernel-source-26.spec.in \
| sed -e "s:@NAME@:kernel-bare-26:g" \
      -e "s:@ARCH@:$PATCH_ARCH:g" \
      -e "s:@CFGNAMES@::g" \
| m4 > $BUILD_DIR/kernel-bare-26.spec

for d in config patches.*; do
    # Skip non-directories. Also work around CVS problem: Directories can't
    # be deleted, but are checked out with only a CVS sub-directory in them.
    DIR_ENTRIES=( $d/* )
    DIR_ENTRIES=${#DIR_ENTRIES[@]}
    if [ ! -d $d -o $DIR_ENTRIES -eq 0 -o \
	 \( -d $d/CVS -a $DIR_ENTRIES -eq 1 \) ] ; then
	echo "Skipping $d..."
	continue
    fi

    echo "Compressing $d..."
    tar -cf - --exclude=CVS --exclude="*~" --exclude=".#*" $d \
    | bzip2 -1 > $BUILD_DIR/$d.tar.bz2
done
if [ -r $SRC_FILE ]; then
	LINUX_ORIG_TARBALL=$SRC_FILE
elif [ -r $MIRROR/$SRC_FILE ]; then
	LINUX_ORIG_TARBALL=$MIRROR/$SRC_FILE
else
	echo "Cannot find $SRC_FILE."
	exit 1
fi
if [ -r $LINUX_ORIG_TARBALL ]; then
	cp -av $LINUX_ORIG_TARBALL $BUILD_DIR/
	echo "done. build dir is now in ./$BUILD_DIR"
else
	echo "done, add $SRC_FILE to ./$BUILD_DIR"
fi
