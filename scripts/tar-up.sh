#!/bin/sh

source $(dirname $0)/config.sh
export LANG=POSIX
SRC_FILE=linux-$VERSION.tar.bz2
ARCHS="i386 ia64 ppc ppc64 s390x x86_64"

while [ $# -gt 0 ]; do
  case $1 in
    --arch=*)
      ARCHS=${1#--arch=}
      ;;
    --arch)
      ARCHS=$2
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

if [ -e scripts/check-conf ]; then
    scripts/check-conf || {
	echo "Inconsistencies found."
	echo "Please clean up series.conf and/or the patches directories!"
	exit
    }
fi

rm -rf kernel-source-26
mkdir kernel-source-26

COMMON_FILES="kernel-source-26.changes \
              series.conf config.conf scripts/merge-headers \
	      scripts/check-for-config-changes \
	      rpm/config_subst.sh rpm/running-kernel.init.in \
	      rpm/functions.sh rpm/post.sh rpm/postun.sh \
	      rpm/trigger-script.sh.in \
	      scripts/guards scripts/arch-symbols"

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
    | bzip2 -1 > kernel-source-26/$d.tar.bz2
  COMMON_FILES="$COMMON_FILES kernel-source-26/$d.tar.bz2"
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
  cp -av $LINUX_ORIG_TARBALL kernel-source-26
  COMMON_FILES="$COMMON_FILES kernel-source-26/${LINUX_ORIG_TARBALL##*/}"
fi

[ -e skip-build ]    && COMMON_FILES="$COMMON_FILES skip-build" 
[ -e extra-symbols ] && COMMON_FILES="$COMMON_FILES extra-symbols"

for ARCH in $ARCHS; do
  export PATCH_ARCH=$ARCH
  SYMBOLS=$(scripts/arch-symbols)
  echo "Architecture symbol(s): $SYMBOLS"
  if [ -s extra-symbols ]; then
    EXTRA_SYMBOLS="$EXTRA_SYMBOLS $(cat extra-symbols)"
  fi
  if [ -n "$EXTRA_SYMBOLS" ]; then
    echo "Extra symbols: $EXTRA_SYMBOLS"
    SYMBOLS="$SYMBOLS $EXTRA_SYMBOLS"
  fi

  case "$PATCH_ARCH" in
    (i?86)	PATCH_ARCH=i386 ;;
    (sun4u)	PATCH_ARCH=sparc64 ;;
    (arm*|sa110) PATCH_ARCH=arm ;;
    (s390x)	PATCH_ARCH=s390 ;;
    (parisc64)	PATCH_ARCH=parisc ;;
  esac

  SUBARCH=$PATCH_ARCH
  BUILD_DIR=kernel-source-26/$PATCH_ARCH

  mkdir $BUILD_DIR

  all_configs=($(scripts/guards --prefix config $SYMBOLS < config.conf))
  # Filter out config/$ARCH/um (User Mode Linux): We do not pre-configure
  # UML kernels.
  configs=(${all_configs[*]/*\/um})

  for config in ${all_configs[*]}; do
    if [ $config = um ]; then
      ARCH=um
    else
      ARCH=$SUBARCH
    fi

    cfgname=${config##*/}
    echo "kernel-$cfgname-26.spec"
    sed -e "s:@NAME@:kernel-$cfgname-26:g" \
    	-e "s:@ARCH@:$ARCH:g" -e "s:@SUBARCH@:$SUBARCH:g" \
	-e "s:@CFGNAME@:$cfgname:g" \
	-e "s:@VERSION@:$VERSION:g" \
      < rpm/kernel-binary-26.spec.in \
      | m4 > $BUILD_DIR/kernel-$cfgname-26.spec
    cat kernel-source-26.changes rpm/kernel-binary-26.changes \
      > $BUILD_DIR/kernel-$cfgname-26.changes
  done

  # The pre-configured kernel source package
  if [ ${#configs[@]} -ne 0 ]; then
    cfgnames="${configs[@]##*/}"
    echo "kernel-source-26.spec"
    sed -e "s:@NAME@:kernel-source-26:g" \
    	-e "s:@ARCH@:$SUBARCH:g" \
	-e "s:@CFGNAMES@:$cfgnames:g" \
	-e "s:@VERSION@:$VERSION:g" \
      < rpm/kernel-source-26.spec.in \
      | m4 > $BUILD_DIR/kernel-source-26.spec
  fi

  # The unconfigured kernel source package: Source for User Mode Linux, and
  # for any km_* packages that absolutely think they need kernel sources
  # installed.
  echo "kernel-bare-26.spec"
  sed -e "s:@NAME@:kernel-bare-26:g" \
      -e "s:@ARCH@:$SUBARCH:g" \
      -e "s:@CFGNAMES@::g" \
      -e "s:@VERSION@:$VERSION:g" \
    < rpm/kernel-source-26.spec.in \
    | m4 > $BUILD_DIR/kernel-bare-26.spec
  cp kernel-source-26.changes $BUILD_DIR/kernel-bare-26.changes

  ln ${COMMON_FILES} $BUILD_DIR
done

if [ ! -r $LINUX_ORIG_TARBALL ]; then
  echo "Please add $SRC_FILE to kernel-source-26/*"
fi
