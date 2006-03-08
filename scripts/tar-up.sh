#!/bin/sh

rpm_release_timestamp=
rpm_release_string=
tolerate_unknown_new_config_options=0
until [ "$#" = "0" ] ; do
  case "$1" in
    --dir=*)
      build_dir=${1#*=}
      shift
      ;;
    -d|--dir)
      build_dir=$2
      shift 2
      ;;
    -nf|--tolerate-unknown-new-config-options)
      tolerate_unknown_new_config_options=1
      shift
      ;;
    -rs|--release-string)
      case "$2" in
      *[' '-]*)
        echo "$1 option argument must not contain dashes or spaces" >&2
	exit 1
	;;
      esac
      rpm_release_string="$2"
      shift 2
      ;;
    -ts|--timestamp)
      rpm_release_timestamp=yes
      shift
      ;;
    -h|--help|-v|--version)
	cat <<EOF

${0##*/} perpares a 'kernel-source' package for submission into autobuild

these options are recognized:
    -rs <string>       to append specified string to rpm release number
    -ts                to use the current date as rpm release number
    -nf                to proceed if a new unknown .config option is found during make oldconfig

EOF
	exit 1
	;;
    *)
      echo "unknown option '$1'" >&2
      exit 1
      ;;
  esac
done
source $(dirname $0)/config.sh
export LANG=POSIX
SRC_FILE=linux-$SRCVERSION.tar.bz2
PATCHVERSION=$($(dirname $0)/compute-PATCHVERSION.sh)
RPMVERSION=${PATCHVERSION//-/_}

if [ -n "$rpm_release_timestamp" ]; then
    if test $(( ${#RPMVERSION} + 10 + 2 + 8 + ${#rpm_release_string})) -gt 64
    then
    	echo "${RPMVERSION}-${rpm_release_string}-\${flavour} exceeds the 64 byte 'uname -r' limit. Use a shorter string."
	exit 1
    fi
    rpm_release_string="\`env -i - TZ=GMT date +%Y%m%d\`${rpm_release_string:+_$rpm_release_string}"
fi

[ -z "$build_dir" ] && build_dir=$BUILD_DIR
if [ -z "$build_dir" ]; then
    echo "Please define the build directory with the --dir option" >&2
    exit 1
fi

check_for_merge_conflicts() {
    set -- $(grep -lP '^<{7}(?!<)|^>{7}(?!>)' "$@" 2> /dev/null)
    if [ $# -gt 0 ]; then
	printf "Merge conflicts in %s\n" "$@" >&2
	return 1
    fi
}

# All config files and patches used
referenced_files="$( {
	$(dirname $0)/guards --list < series.conf
	$(dirname $0)/guards --prefix=config --list < config.conf
    } | sort -u )"

if ! check_for_merge_conflicts $referenced_files \
			       kernel-source.changes \
			       kernel-source.changes.old || \
   ! scripts/check-conf || \
   ! scripts/check-cvs-add; then
    echo "Inconsistencies found."
    echo "Please clean up series.conf and/or the patches directories!"
    echo "Press <ENTER> to continue"
    read
fi

rm -rf $build_dir
mkdir -p $build_dir

echo "Computing timestamp..."
if ! scripts/cvs-wd-timestamp > $build_dir/build-source-timestamp; then
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
	echo $tag >> $build_dir/build-source-timestamp
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
	    extra_needs="libpcap xorg-x11-devel" ;;
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
	    cp $arch-$flavor.conf $build_dir/
	fi
	if [ -e $arch-$flavor.diff ]; then
	    echo "Extra patch: $arch-$flavor.diff"
	    cp $arch-$flavor.diff $build_dir/
	fi

	[ $arch = i386 ] && arch="%ix86"
	nl=$'\n'
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
	-e "s,@FLAVOR@,$flavor,g" \
	-e "s,@SRCVERSION@,$SRCVERSION,g" \
	-e "s,@PATCHVERSION@,$PATCHVERSION,g" \
	-e "s,@RPMVERSION@,$RPMVERSION,g" \
	-e "s,@ARCHS@,$archs,g" \
	-e "s,@PROVIDES_OBSOLETES@,${prov_obs//$'\n'/\\n},g" \
	-e "s,@EXTRA_NEEDS@,$extra_needs,g" \
	-e "s,@TOLERATE_UNKNOWN_NEW_CONFIG_OPTIONS@,$tolerate_unknown_new_config_options,g" \
      < rpm/kernel-binary.spec.in \
    > $build_dir/kernel-$flavor.spec
    case "$flavor" in
    	ppc64|iseries64|kdump)
	sed -i '/^# norootforbuild/ {
	a \
# icecream 0\

	}' $build_dir/kernel-$flavor.spec
	;;
    esac
done

install_changes() {
    local changes=$1
    cat kernel-source.changes kernel-source.changes.old > $changes
    chmod 644 $changes
}

for flavor in $flavors ; do
    install_changes $build_dir/kernel-$flavor.changes
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
    -e "s,@SRCVERSION@,$SRCVERSION,g" \
    -e "s,@PATCHVERSION@,$PATCHVERSION,g" \
    -e "s,@RPMVERSION@,$RPMVERSION,g" \
    -e "s,@PRECONF@,1,g" \
    -e "s,@BINARY_SPEC_FILES@,$binary_spec_files,g" \
    -e "s,@TOLERATE_UNKNOWN_NEW_CONFIG_OPTIONS@,$tolerate_unknown_new_config_options," \
  < rpm/kernel-source.spec.in \
> $build_dir/kernel-source.spec

echo "kernel-dummy.spec"
sed -e "s,@NAME@,kernel-dummy,g" \
    -e "s,@SRCVERSION@,$SRCVERSION,g" \
    -e "s,@PATCHVERSION@,$PATCHVERSION,g" \
    -e "s,@RPMVERSION@,$RPMVERSION,g" \
  < rpm/kernel-dummy.spec.in \
> $build_dir/kernel-dummy.spec

# Compute @BUILD_REQUIRES@ expansion
head="" ; tail=""
for arch in $(scripts/arch-symbols --list) ; do
    set -- $(scripts/guards $(scripts/arch-symbols $arch) < config.conf \
	     | sed -e 's:.*/:kernel-:')
    [ $arch = i386 ] && arch="%ix86"
    nl=$'\n'
    if [ $# -gt 0 ]; then
	[ -n "$head" ] && head="${head}%else$nl"
	head="${head}%ifarch $arch$nl"
	head="${head}BuildRequires: $*$nl"
	tail="%endif$nl$tail"
    fi
done
build_req="$head${tail%$'\n'}"

echo "kernel-syms.spec"
sed -e "s,@NAME@,kernel-syms,g" \
    -e "s,@SRCVERSION@,$SRCVERSION,g" \
    -e "s,@PATCHVERSION@,$PATCHVERSION,g" \
    -e "s,@RPMVERSION@,$RPMVERSION,g" \
    -e "s,@BUILD_REQUIRES@,${build_req//$'\n'/\\n},g" \
    -e "s,@PRECONF@,1,g" \
  < rpm/kernel-syms.spec.in \
> $build_dir/kernel-syms.spec

install_changes $build_dir/kernel-syms.changes

echo "Copying various files..."
install -m 644					\
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
	$build_dir
install_changes $build_dir/kernel-source.changes
install_changes $build_dir/kernel-dummy.changes

install -m 755					\
	rpm/find-provides			\
	rpm/config-subst 			\
	rpm/prepare-build.sh			\
	rpm/check-for-config-changes		\
	rpm/check-supported-list		\
	rpm/check-build.sh			\
	rpm/install-configs			\
	rpm/find-types				\
	rpm/built-in-where			\
	rpm/make-symsets			\
	scripts/guards				\
	scripts/arch-symbols			\
	scripts/kabi-checks			\
	misc/extract-modaliases			\
	$build_dir

if [ -e extra-symbols ]; then
	install -m 755					\
		extra-symbols				\
		$build_dir
fi

if [ -z "$rpm_release_string" ]; then
    install -m 755					\
	rpm/get_release_number.sh			\
	$build_dir
else
    cat > $build_dir/get_release_number.sh <<-EOF
	#!/bin/sh
	echo "$rpm_release_string"
	EOF
    chmod a+rx $build_dir/get_release_number.sh
fi

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
echo $SRC_FILE
cp $LINUX_ORIG_TARBALL $build_dir

# The first directory level determines the archive name
all_archives="$(
    echo "$referenced_files" \
    | sed -e 's,/.*,,' \
    | uniq )"
for archive in $all_archives; do
    echo "$archive.tar.bz2"
    case " $IGNORE_ARCHS " in
    *" ${archive#patches.} "*)
	echo "Ignoring $d..."
	continue ;;
    esac

    files="$( echo "$referenced_files" \
	| sed -ne "\:^${archive//./\\.}/:p" \
	| while read patch; do
	    [ -e "$patch" ] && echo "$patch"
	done)"
    if [ -n "$files" ]; then
	tar -cf - $files \
	| bzip2 -9 > $build_dir/$archive.tar.bz2
    fi
done

echo "kabi.tar.bz2"
tar cf - --exclude CVS kabi \
| bzip2 -9 > $build_dir/kabi.tar.bz2

echo "novell-kmp.tar.bz2"
(   cd doc
    tar -cf - --exclude=CVS --exclude='.*.cmd' \
	      --exclude='*.ko' --exclude='*.o' novell-kmp
) | bzip2 > $build_dir/novell-kmp.tar.bz2

# Create empty dummys for any *.tar.bz2 archive mentioned in the spec file
# not already created: patches.addon is empty by intention; others currently
# may contain no patches.
archives=$(sed -ne 's,^Source[0-9]*:.*[ \t/]\([^/]*\)\.tar\.bz2$,\1,p' \
           $build_dir/*.spec | sort -u)
for archive in $archives; do
    if ! [ -e $build_dir/$archive.tar.bz2 ]; then
	echo "$archive.tar.bz2 (empty)"
	bzip2 -9 < /dev/null > $build_dir/$archive.tar.bz2
    fi
done

# Force mbuild to choose build hosts with enough memory available:
echo $((1024*1024)) > $build_dir/minmem
# Force mbuild to choose build hosts with enough disk space available:
echo $((3*1024)) > $build_dir/needed_space_in_mb
