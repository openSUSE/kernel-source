#!/bin/sh

source $(dirname $0)/config.sh
export LANG=POSIX
SRC_FILE=linux-$VERSION.tar.bz2

if [ -e scripts/check-conf ]; then
    scripts/check-conf || {
	echo "Inconsistencies found."
	echo "Please clean up series.conf and/or the patches directories!"
	exit
    }
fi

rm -rf $BUILD_DIR
mkdir -p $BUILD_DIR

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
fi

#echo "Copying various files..."
cp -pv	kernel-source-26.changes \
	series.conf config.conf scripts/merge-headers \
	scripts/check-for-config-changes \
	rpm/config_subst.sh rpm/running-kernel.init.in \
	rpm/functions.sh rpm/post.sh rpm/postun.sh \
	rpm/trigger-script.sh.in \
	scripts/guards scripts/arch-symbols $BUILD_DIR

[ -e extra-symbols ] && cp -pv extra-symbols $BUILD_DIR

# List all used configurations
config_files="$(
    for arch in $(scripts/arch-symbols --list) ; do
	scripts/guards $(scripts/arch-symbols $arch) < config.conf \
	| sed -e "s:^:$arch :"
    done)"
cfgnames="$(echo "$config_files" | sed -e 's:.*/::' | sort -u)"

for cfgname in $cfgnames ; do
    echo "kernel-$cfgname-26.spec"

    set -- $(
	echo "$config_files" \
	| sed -e "/\/$cfgname/!d" \
	      -e "s: .*::g" \
	      -e "s:i386:%ix86:g" \
	| sort -u)
    archs="$*"
    
    cat rpm/kernel-binary-26.spec.in \
    | sed -e "s:@NAME@:kernel-$cfgname-26:g" \
	  -e "s:@CFGNAME@:$cfgname:g" \
	  -e "s:@VERSION@:$VERSION:g" \
	  -e "s:@ARCHS@:$archs:g" \
    | m4 > $BUILD_DIR/kernel-$cfgname-26.spec
    cat kernel-source-26.changes rpm/kernel-binary-26.changes \
      > $BUILD_DIR/kernel-$cfgname-26.changes
  done

# The pre-configured kernel source package
echo "kernel-source-26.spec"
cat rpm/kernel-source-26.spec.in \
| sed -e "s:@NAME@:kernel-source-26:g" \
      -e "s:@VERSION@:$VERSION:g" \
      -e "s:@PRECONF@:1:g" \
| m4 > $BUILD_DIR/kernel-source-26.spec

# The unconfigured kernel source package: Source for User Mode Linux, and
# for any km_* packages that absolutely think they need kernel sources
# installed.
echo "kernel-bare-26.spec"
cat rpm/kernel-source-26.spec.in \
| sed -e "s:@NAME@:kernel-bare-26:g" \
      -e "s:@VERSION@:$VERSION:g" \
      -e "s:@PRECONF@:0:g" \
| m4 > $BUILD_DIR/kernel-bare-26.spec
cp kernel-source-26.changes $BUILD_DIR/kernel-bare-26.changes

if [ ! -r $LINUX_ORIG_TARBALL ]; then
  echo "Please add $SRC_FILE to kernel-source-26/*"
fi
