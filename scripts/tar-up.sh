#!/bin/sh

source $(dirname $0)/config.sh
export LANG=POSIX
SRC_FILE=linux-$VERSION.tar.bz2

if [ -e scripts/check-conf ]; then
    scripts/check-conf || {
	echo "Inconsistencies found."
	echo "Please clean up series.conf and/or the patches directories!"
	read
    }
fi

rm -rf $BUILD_DIR
mkdir -p $BUILD_DIR

# List all used configurations
config_files="$(
    for arch in $(scripts/arch-symbols --list) ; do
	scripts/guards $(scripts/arch-symbols $arch) < config.conf \
	| sed -e "s,^,$arch ,"
    done)"
flavors="$(echo "$config_files" | sed -e 's,.*/,,' | sort -u)"

for flavor in $flavors ; do
    echo "kernel-$flavor.spec"

    # Find all architectures for this spec file
    set -- $(
	echo "$config_files" \
	| sed -e "/\/$flavor/!d" \
	      -e "s, .*,,g" \
	| sort -u)
    archs="$*"
    
    # Compute @PROVIDES_OBSOLETES@ expansion
    head="" ; tail=""
    for arch in $archs ; do
	p=( $(scripts/guards $(scripts/arch-symbols $arch) $flavor p \
		< rpm/old-packages.conf) )
	o=( $(scripts/guards $(scripts/arch-symbols $arch) $flavor o \
		< rpm/old-packages.conf) )

	[ $arch = i386 ] && arch="%ix86" && nl=$'\n'
	if [ ${#p[@]} -o ${#p[@]} ]; then
	    [ -n "$head" ] && head="${head}%else$nl"
	    head="${head}%ifarch $arch$nl"
	    [ -n "$p" ] && head="${head}Provides:     ${p[@]}$nl"
	    [ -n "$o" ] && head="${head}Obsoletes:    ${o[@]}$nl"
	    tail="%endif$nl$tail"
	fi

	# Do we have an override config file for testing?
	if [ -e $arch-$flavor.conf ]; then
	    echo "Override config: $arch-$flavor.conf"
	    cp $arch-$flavor.conf $BUILD_DIR/
	fi
    done
    prov_obs="$head${tail%$'\n'}"

    # If we build this spec file for only one architecture,  the
    # enclosing if is not needed
    if [ $(set -- $archs ; echo $#) -eq 1 ]; then
	prov_obs="$(echo "$prov_obs" | grep -v '%ifarch\|%endif')"
    fi

    # In ExclusiveArch in the spec file, we must specify %ix86 instead
    # of i386.
    archs="$(echo $archs | sed -e 's,i386,%ix86,g')"

    # Generate spec file
    sed -e "s,@NAME@,kernel-$flavor,g" \
	-e "s,@CFGNAME@,$flavor,g" \
	-e "s,@VERSION@,$VERSION,g" \
	-e "s,@ARCHS@,$archs,g" \
	-e "s,@PROVIDES_OBSOLETES@,${prov_obs//$'\n'/\\n},g" \
      < rpm/kernel-binary.spec.in \
    > $BUILD_DIR/kernel-$flavor.spec
    cp kernel-source.changes $BUILD_DIR/kernel-$flavor.changes
done

# The pre-configured kernel source package
echo "kernel-source.spec"
sed -e "s,@NAME@,kernel-source,g" \
    -e "s,@VERSION@,$VERSION,g" \
    -e "s,@PRECONF@,1,g" \
  < rpm/kernel-source.spec.in \
> $BUILD_DIR/kernel-source.spec

## The unconfigured kernel source package: Source for User Mode Linux, and
## for any km_* packages that absolutely think they need kernel sources
## installed.
#echo "kernel-bare.spec"
#sed -e "s,@NAME@,kernel-bare,g" \
#    -e "s,@VERSION@,$VERSION,g" \
#    -e "s,@PRECONF@,0,g" \
#  < rpm/kernel-source.spec.in \
#> $BUILD_DIR/kernel-bare.spec
#cp kernel-source.changes $BUILD_DIR/kernel-bare.changes

echo "kernel-syms.spec"
sed -e "s,@NAME@,kernel-syms,g" \
    -e "s,@VERSION@,$VERSION,g" \
    -e "s,@PRECONF@,1,g" \
  < rpm/kernel-syms.spec.in \
> $BUILD_DIR/kernel-syms.spec
cp kernel-source.changes $BUILD_DIR/kernel-syms.changes

echo "Copying various files..."
install -m 644					\
	kernel-source.changes			\
	series.conf				\
	config.conf				\
	rpm/running-kernel.init.in		\
	rpm/functions.sh			\
	rpm/trigger-script.sh.in		\
	rpm/source-post.sh			\
	rpm/post.sh				\
	rpm/postun.sh				\
	$BUILD_DIR

install -m 755					\
	rpm/config-subst 			\
	rpm/get_release_number.sh		\
	rpm/merge-headers			\
	rpm/check-for-config-changes		\
	scripts/guards				\
	scripts/arch-symbols			\
	$BUILD_DIR

#cp -pv	kernel-source.changes \
#	series.conf config.conf rpm/merge-headers \
#	rpm/check-for-config-changes \
#	rpm/config-subst rpm/running-kernel.init.in \
#	rpm/functions.sh rpm/post.sh rpm/postun.sh \
#	rpm/trigger-script.sh.in rpm/get_release_number.sh \
#	scripts/guards scripts/arch-symbols $BUILD_DIR

if [ -e extra-symbols ]; then
	install -m 755					\
		extra-symbols				\
		$BUILD_DIR
fi

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
  cp -av $LINUX_ORIG_TARBALL $BUILD_DIR
fi

if [ ! -r $LINUX_ORIG_TARBALL ]; then
  echo "Please add $SRC_FILE to $BUILD_DIR"
fi
