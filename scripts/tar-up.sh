#!/bin/sh

rpm_release_timestamp=
until [ "$#" = "0" ] ; do
  case "$1" in
    -ts|--timestamp)
      rpm_release_timestamp=yes
      shift
      ;;
    *)
      shift
      ;;
  esac
done
source $(dirname $0)/config.sh
export LANG=POSIX
SRC_FILE=linux-$VERSION.tar.bz2
_VERSION=${VERSION//-/_}

if ! scripts/check-conf || \
   ! scripts/check-cvs-add; then
    echo "Inconsistencies found."
    echo "Please clean up series.conf and/or the patches directories!"
    echo "Press <ENTER> to continue"
    read
fi

rm -rf $BUILD_DIR
mkdir -p $BUILD_DIR

echo "Computing timestamp..."
if ! scripts/cvs-wd-timestamp > $BUILD_DIR/build-source-timestamp; then
    exit 1
fi

# If we are on a CVS branch, included the branch name as well:
if [ -e CVS/Tag ]; then
    read tag < CVS/Tag
    case "$tag" in
    T*)	tag="CVS Branch: ${tag:1}" ;;
    N*)	tag="CVS Tag: ${tag:1}" ;;
    D*)	tag="CVS Date: ${tag:1}" ;;
    *)	tag=
    esac
    if [ -n "$tag" ]; then
	echo $tag >> $BUILD_DIR/build-source-timestamp
    fi
fi

# List all used configurations
config_files="$(
    for arch in $(scripts/arch-symbols --list) ; do
	scripts/guards $(scripts/arch-symbols $arch) < config.conf \
	| sed -e "s,^,$arch ,"
    done)"
flavors="$(echo "$config_files" | sed -e 's,.*/,,' | sort -u)"

for flavor in $flavors ; do
    echo "kernel-$flavor.spec"

    extra_needs=
    case $flavor in
	um)
	    extra_needs=x-devel-packages ;;
    esac
    use_icecream=1
    case $flavor in
	pseries64|pmac64|iseries64)
	    use_icecream=0 ;;
    esac

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

	# Do we have an override config file or an additional patch?
	if [ -e $arch-$flavor.conf ]; then
	    echo "Override config: $arch-$flavor.conf"
	    cp $arch-$flavor.conf $BUILD_DIR/
	fi
	if [ -e $arch-$flavor.diff ]; then
	    echo "Extra patch: $arch-$flavor.diff"
	    cp $arch-$flavor.diff $BUILD_DIR/
	fi

	[ $arch = i386 ] && arch="%ix86" && nl=$'\n'
	if [ ${#p[@]} -o ${#p[@]} ]; then
	    [ -n "$head" ] && head="${head}%else$nl"
	    head="${head}%ifarch $arch$nl"
	    [ -n "$p" ] && head="${head}Provides:     ${p[@]}$nl"
	    [ -n "$o" ] && head="${head}Obsoletes:    ${o[@]}$nl"
	    tail="%endif$nl$tail"
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
	-e "s,@ICECREAM@,$use_icecream,g" \
	-e "s,@CFGNAME@,$flavor,g" \
	-e "s,@VERSION@,$_VERSION,g" \
	-e "s,@ARCHS@,$archs,g" \
	-e "s,@PROVIDES_OBSOLETES@,${prov_obs//$'\n'/\\n},g" \
	-e "s,@EXTRA_NEEDS@,$extra_needs,g" \
      < rpm/kernel-binary.spec.in \
    > $BUILD_DIR/kernel-$flavor.spec
    case $flavor in
	(xen*)
		# We don't compete with a normal kernel
		sed -i 's/^Provides: *kernel/Provides: xenkernel/' $BUILD_DIR/kernel-$flavor.spec
 	;;
    esac
    cp kernel-source.changes $BUILD_DIR/kernel-$flavor.changes
done

binary_spec_files=$(
    n=50
    for flavor in syms $flavors ; do
	printf "%-14s%s\n" "Source$n:" "kernel-$flavor.spec"
	n=$[$n+1]
    done
)
binary_spec_files=${binary_spec_files//$'\n'/\\n}

# The pre-configured kernel source package
echo "kernel-source.spec"
sed -e "s,@NAME@,kernel-source,g" \
    -e "s,@VERSION@,$_VERSION,g" \
    -e "s,@PRECONF@,1,g" \
    -e "s,@BINARY_SPEC_FILES@,$binary_spec_files,g" \
  < rpm/kernel-source.spec.in \
> $BUILD_DIR/kernel-source.spec

echo "kernel-dummy.spec"
sed -e "s,@NAME@,kernel-dummy,g" \
    -e "s,@VERSION@,$_VERSION,g" \
  < rpm/kernel-dummy.spec.in \
> $BUILD_DIR/kernel-dummy.spec

echo "kernel-syms.spec"
sed -e "s,@NAME@,kernel-syms,g" \
    -e "s,@VERSION@,$_VERSION,g" \
    -e "s,@PRECONF@,1,g" \
  < rpm/kernel-syms.spec.in \
> $BUILD_DIR/kernel-syms.spec
cp kernel-source.changes $BUILD_DIR/kernel-syms.changes

echo "Copying various files..."
install -m 644					\
	kernel-source.changes			\
	series.conf				\
	config.conf				\
	supported.conf				\
	rpm/running-kernel.init.in		\
	rpm/functions.sh			\
	rpm/trigger-script.sh.in		\
	rpm/source-post.sh			\
	rpm/post.sh				\
	rpm/postun.sh				\
	rpm/Makefile.suse			\
	doc/README.SUSE				\
	$BUILD_DIR

install -m 644					\
	kernel-source.changes 			\
	$BUILD_DIR/kernel-dummy.changes

install -m 755					\
	rpm/config-subst 			\
	rpm/get_release_number.sh		\
	rpm/prepare-build.sh			\
	rpm/check-for-config-changes		\
	rpm/check-supported-list		\
	rpm/check-build.sh			\
	scripts/guards				\
	scripts/arch-symbols			\
	rpm/install-configs			\
	$BUILD_DIR

if [ -e extra-symbols ]; then
	install -m 755					\
		extra-symbols				\
		$BUILD_DIR
fi

echo "hello.tar.bz2"
(   cd doc
    tar -cf - --exclude=CVS --exclude='.*.cmd' \
    	      --exclude='*.ko' --exclude='*.o' hello
) | bzip2 > $BUILD_DIR/hello.tar.bz2

# Generate list of all config files and patches used
all_files="$( {
	$(dirname $0)/guards --list < series.conf
	$(dirname $0)/guards --prefix=config --list < config.conf
    } | sort -u )"
# The first directory level determines the archive name
all_archives="$(
    echo "$all_files" \
    | sed -e 's,/.*,,' \
    | uniq )"
for archive in $all_archives ; do
    echo "$archive.tar.bz2"
    case " $IGNORE_ARCHS " in
    *" ${archive#patches.} "*)
	echo "Ignoring $d..."
	continue ;;
    esac

    files="$( echo "$all_files" \
	| sed -ne "\:^${archive//./\\.}/:p" \
	| while read patch; do
	    [ -e "$patch" ] && echo "$patch"
	done)"
    tar -cf - $files \
    | bzip2 -9 > $BUILD_DIR/$archive.tar.bz2
done
bzip2 -9 < /dev/null > $BUILD_DIR/patches.addon.tar.bz2

if [ -r $SRC_FILE ]; then
  LINUX_ORIG_TARBALL=$SRC_FILE
elif [ -r $MIRROR/$SRC_FILE ]; then
  LINUX_ORIG_TARBALL=$MIRROR/$SRC_FILE
elif [ -r $MIRROR/testing/$SRC_FILE ]; then
  LINUX_ORIG_TARBALL=$MIRROR/testing/$SRC_FILE
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

if [ "$rpm_release_timestamp" = "yes" ] ; then
cat > $BUILD_DIR/get_release_number.sh <<EOF
#!/bin/sh
env -i - TZ=GMT date +%Y%m%d
EOF
chmod -v a+rx $BUILD_DIR/get_release_number.sh
fi

echo "If you want to submit the kernel to Autobuild now,"
echo "how about running \`mbuild --obey-doesnotbuild' before?"
