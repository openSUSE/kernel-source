#!/bin/sh
# $Version$

source `dirname $0`/config.sh

SRC_FILE=linux-$VERSION.tar.bz2

if [ -e scripts/check-patches ]; then
    scripts/check-patches || {
	echo "Inconsistencies found."
	echo "Please clean up series.conf and/or the patches directories!"
	read
    }
fi

rm -rf $BUILD_DIR
mkdir -p $BUILD_DIR

cp -pv README* kernel-source*.spec kernel-source*.changes \
	series.conf config.conf \
	scripts/guards scripts/arch-symbols $BUILD_DIR

[ -e skip-build ]    && cp -pv skip-build    $BUILD_DIR 
[ -e k_smp.tgz ]     && cp -pv k_smp.tgz     $BUILD_DIR 
[ -e k_deflt.tgz ]   && cp -pv k_deflt.tgz   $BUILD_DIR 
[ -e extra-symbols ] && cp -pv extra-symbols $BUILD_DIR

for d in config patches.*; do
    # Skip non-directories. Also work around CVS problem: Directories can't
    # be deleted, but are checked out with only a CVS sub-directory in them.
    DIR_ENTRIES=( $d/* )
    DIR_ENTRIES=${#DIR_ENTRIES[@]}
    if test \! -d $d -o $DIR_ENTRIES -eq 0 -o \
	    \( -d $d/CVS -a $DIR_ENTRIES -eq 1 \) ; then
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
fi
if [ -r $LINUX_ORIG_TARBALL ]; then
	cp -av $LINUX_ORIG_TARBALL $BUILD_DIR/
	echo "done. build dir is now in ./$BUILD_DIR"
else
	echo "done, add $SRC_FILE to ./$BUILD_DIR"
fi

if [ "$1" = -n ]; then
	cd $BUILD_DIR
	build kernel-source.spec --noinit
fi
