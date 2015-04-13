#!/bin/bash

#############################################################################
# Copyright (c) 2003-2009 Novell, Inc.
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

# generate a kernel-source rpm package

. ${0%/*}/wd-functions.sh

sort()
{
	LC_ALL=C command sort "$@"
}

rpm_release_timestamp=
rpm_release_string=
source_timestamp=
tolerate_unknown_new_config_options=0
ignore_kabi=
ignore_unsupported_deps=
source rpm/config.sh
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
    --embargo)
      embargo_filter=1
      shift
      ;;
    -nf|--tolerate-unknown-new-config-options)
      tolerate_unknown_new_config_options=1
      shift
      ;;
    -i|--ignore-kabi)
      ignore_kabi=1
      shift
      ;;
    -iu|--ignore-unsupported-deps)
      ignore_unsupported_deps=1
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
    -k|--kbuild|--source-timestamp)
      source_timestamp=1
      shift
      ;;
    -h|--help|-v|--version)
	cat <<EOF

${0##*/} perpares a 'kernel-source' package for submission into autobuild

these options are recognized:
    -rs <string>       to append specified string to rpm release number
    -ts                to use the current date as rpm release number
    -nf                to proceed if a new unknown .config option is found during make oldconfig
    -i                 ignore kabi failures
    --source-timestamp to autogenerate a release number based on branch and timestamp (overrides -rs/-ts)
    -d, --dir=DIR      create package in DIR instead of default kernel-source$VARIANT

EOF
	exit 1
	;;
    *)
      echo "unknown option '$1'" >&2
      exit 1
      ;;
  esac
done
export LANG=POSIX
if test -e scripts/compute-PATCHVERSION.sh; then
    PATCHVERSION=$($(dirname $0)/compute-PATCHVERSION.sh)

    case "$PATCHVERSION" in
    *-*)
        RPMVERSION=${PATCHVERSION%%-*}
        RELEASE_PREFIX=${PATCHVERSION#*-}.
        RELEASE_PREFIX=${RELEASE_PREFIX//-/.}
        ;;
    *)
        RPMVERSION=$PATCHVERSION
        RELEASE_PREFIX=
        ;;
    esac
fi

if [ -n "$rpm_release_timestamp" ]; then
    if test $(( ${#RPMVERSION} + 10 + 2 + 8 + ${#rpm_release_string})) -gt 64
    then
    	echo "${RPMVERSION}-${rpm_release_string}-\${flavour} exceeds the 64 byte 'uname -r' limit. Use a shorter string."
	exit 1
    fi
    rpm_release_string="\`env -i - TZ=GMT date +%Y%m%d\`${rpm_release_string:+_$rpm_release_string}"
fi

[ -z "$build_dir" ] && build_dir=kernel-source$VARIANT
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

# Dot files are skipped by intention, in order not to break osc working
# copies. The linux tarball is not deleted if it is already there
for f in "$build_dir"/*; do
	case "$f" in
	*/"linux-$SRCVERSION.tar.bz2")
		continue
	esac
	rm -f "$f"
done
mkdir -p "$build_dir"
echo "linux-$SRCVERSION.tar.bz2"
get_tarball "$SRCVERSION" "tar.bz2" "$build_dir"

# list of patches to include.
install -m 644 series.conf $build_dir/

# All config files and patches used
referenced_files="$( {
	$(dirname $0)/guards --list < $build_dir/series.conf
	$(dirname $0)/guards --prefix=config --list < config.conf
    } | sort -u )"

for file in $referenced_files; do
	case $file in
	config/* | patches.*/*)
		;;
	*)
		echo "Error: Patches must be placed in the patches.*/ subdirectories: $file" >&2
		exit 1
	esac
done
inconsistent=false
check_for_merge_conflicts $referenced_files kernel-source.changes{,.old} || \
	inconsistent=true
scripts/check-conf || inconsistent=true
scripts/check-cvs-add --committed || inconsistent=true
# FIXME: someone should clean up the mess and make this check fatal
if $inconsistent; then
    echo "Inconsistencies found."
    echo "Please clean up series.conf and/or the patches directories!"
    echo
fi

tsfile=build-source-timestamp
if ! scripts/cvs-wd-timestamp > $build_dir/$tsfile; then
    exit 1
fi

if $using_git; then
    # Always include the git revision
    echo "GIT Revision: $(git rev-parse HEAD)" >> $build_dir/$tsfile
    tag=$(get_branch_name)
    if test -n "$tag"; then
	echo "GIT Branch: $tag" >>$build_dir/$tsfile
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
	    extra_needs="BuildRequires:  libpcap xorg-x11-devel" ;;
    esac

    # Find all architectures for this spec file
    set -- $(
	echo "$config_files" \
	| sed -e "/\/$flavor\$/!d" \
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

    # Special km modules for this kernel (SLES9)
    if test -e rpm/km.conf; then
        set -- $(scripts/guards $(
                    for arch in $archs; do
                        scripts/arch-symbols $arch
                    done
                    ) $flavor < rpm/km.conf)
        extra_kms=$*
    else
        extra_kms=
    fi

    # In ExclusiveArch in the spec file, we must specify %ix86 instead
    # of i386.
    archs="$(echo $archs | sed -e 's,i386,%ix86,g')"

    # Summary and description
    if test -e rpm/package-descriptions; then
	description=$(sed "1,/^=== kernel-$flavor ===/d; /^===/,\$ d" rpm/package-descriptions)
	if test -z "$description"; then
	    echo "warning: no description for kernel-$flavor found" >&2
	    summary="The Linux Kernel"
	    description="The Linux Kernel."
	else
	    summary=$(echo "$description"  | head -n 1)
	    # escape newlines for the sed 's' command
	    description=$(echo "$description" | tail -n +3 | \
		sed 's/$/\\/; $ s/\\$//')
	fi
    else
	summary="The Linux Kernel"
	description="The Linux Kernel."
    fi

    # Generate spec file
    sed -r -e "s,@NAME@,kernel-$flavor,g" \
	-e "s,@SUMMARY@,$summary,g" \
	-e "s~@DESCRIPTION@~$description~g" \
	-e "s,@(FLAVOR|CFGNAME)@,$flavor,g" \
	-e "s,@VARIANT@,$VARIANT,g" \
	-e "s,@(SRC)?VERSION@,$SRCVERSION,g" \
	-e "s,@PATCHVERSION@,$PATCHVERSION,g" \
	-e "s,@RPMVERSION@,$RPMVERSION,g" \
	-e "s,@PRECONF@,1,g" \
	-e "s,@NO_DEBUG@,,g" \
	-e "s,@KERNEL_MODULE_PACKAGES@,kernel-module-packages,g" \
	-e "s,@EXTRA_KMS@,$extra_kms,g" \
	-e "s,@ARCHS@,$archs,g" \
	-e "s,@PROVIDES_OBSOLETES@,${prov_obs//$'\n'/\\n},g" \
	-e "s,@EXTRA_NEEDS@,$extra_needs,g" \
	-e "s,@TOLERATE_UNKNOWN_NEW_CONFIG_OPTIONS@,$tolerate_unknown_new_config_options,g" \
	-e "s,@RELEASE_PREFIX@,$RELEASE_PREFIX,g" \
      < rpm/kernel-binary.spec.in \
    > $build_dir/kernel-$flavor.spec
done

install_changes() {
    local changes=$1
    cat kernel-source.changes > "$changes"
    if test -e kernel-source.changes.old; then
        cat "$_" >>"$changes"
    fi
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
binary_spec_files_list=$(
    for flavor in syms $flavors; do
        echo -n "kernel-$flavor.spec "
    done
)

CLEANFILES=()
trap 'if test -n "$CLEANFILES"; then rm -rf "${CLEANFILES[@]}"; fi' EXIT
tmpdir=$(mktemp -dt ${0##*/}.XXXXXX)
CLEANFILES=("${CLEANFILES[@]}" "$tmpdir")

EXTRA_SYMBOLS=$([ -e extra-symbols ] && cat extra-symbols)

# Compute @BUILD_REQUIRES@ expansion
prepare_source_and_syms() {
    local name=$1
    local head="" tail="" nl ARCH_SYMBOLS packages flavor av arch build_req

    archs=
    build_requires=

    for arch in $(scripts/arch-symbols --list); do
	ARCH_SYMBOLS=$(scripts/arch-symbols $arch)

	# Exclude flavors that have a different set of patches: we assume that
	# the user won't change series.conf so much that two flavors that differ
	# at tar-up.sh time will become identical later.

	set -- $ARCH_SYMBOLS $EXTRA_SYMBOLS
	case $name in
	(*-rt)
	    set -- RT "$@"
	    ;;
	esac
	scripts/guards "$@" < series.conf > $tmpdir/$name.patches

	packages=
	for arch_flavor in $(scripts/guards $ARCH_SYMBOLS $EXTRA_SYMBOLS syms \
				< config.conf); do
	    flavor=${arch_flavor#*/}
	    av=${arch_flavor//\//_}
	    set -- kernel-$flavor $flavor \
		   $(case $flavor in (rt|rt_*) echo RT ;; esac)

	    # The patch selection for kernel-vanilla is a hack.
	    [ $flavor = vanilla ] && continue

	    scripts/guards $* $ARCH_SYMBOLS $EXTRA_SYMBOLS < series.conf \
		> $tmpdir/kernel-$av.patches
	    diff -q $tmpdir/{$name,kernel-$av}.patches > /dev/null \
		|| continue
	    packages="$packages kernel-$flavor"
	done

	set -- $packages
	if [ $# -gt 0 ]; then
	    [ $arch = i386 ] && arch="%ix86"
	    nl=$'\n'
	    [ -n "$head" ] && head="${head}%else$nl"
	    head="${head}%ifarch $arch$nl"
	    head="${head}BuildRequires: $*$nl"
	    tail="%endif$nl$tail"
	    archs="$archs $arch"
	fi
    done
    build_requires="$head${tail%$'\n'}"
    build_requires="${build_requires//$'\n'/\\n}"
    archs=${archs# }
}

echo "kernel-source.spec"
prepare_source_and_syms kernel-syms # compute archs and build_requires
sed -r -e "s,@NAME@,kernel-source,g" \
    -e "s,@(SRC)?VERSION@,$SRCVERSION,g" \
    -e "s,@PATCHVERSION@,$PATCHVERSION,g" \
    -e "s,@RPMVERSION@,$RPMVERSION,g" \
    -e "s,@PRECONF@,1,g" \
    -e "s,@ARCHS@,$archs,g" \
    -e "s,@BINARY_SPEC_FILES@,$binary_spec_files,g" \
    -e "s,@BINARY_SPEC_FILES_LIST@,$binary_spec_files_list,g" \
    -e "s,@TOLERATE_UNKNOWN_NEW_CONFIG_OPTIONS@,$tolerate_unknown_new_config_options," \
    -e "s,@RELEASE_PREFIX@,$RELEASE_PREFIX,g" \
  < rpm/kernel-source.spec.in \
> $build_dir/kernel-source.spec
install_changes $build_dir/kernel-source.changes

echo "kernel-syms.spec"
sed -r -e "s,@NAME@,kernel-syms,g" \
    -e "s,@VARIANT@,,g" \
    -e "s,@(SRC)?VERSION@,$SRCVERSION,g" \
    -e "s,@PATCHVERSION@,$PATCHVERSION,g" \
    -e "s,@RPMVERSION@,$RPMVERSION,g" \
    -e "s,@PRECONF@,1,g" \
    -e "s,@ARCHS@,$archs,g" \
    -e "s,@BUILD_REQUIRES@,$build_requires,g" \
    -e "s,@RELEASE_PREFIX@,$RELEASE_PREFIX,g" \
  < rpm/kernel-syms.spec.in \
> $build_dir/kernel-syms.spec
install_changes $build_dir/kernel-syms.changes

echo "kernel-dummy.spec"
sed -r -e "s,@NAME@,kernel-dummy,g" \
    -e "s,@(SRC)?VERSION@,$SRCVERSION,g" \
    -e "s,@PATCHVERSION@,$PATCHVERSION,g" \
    -e "s,@RPMVERSION@,$RPMVERSION,g" \
    -e "s,@RELEASE_PREFIX@,$RELEASE_PREFIX,g" \
  < rpm/kernel-dummy.spec.in \
> $build_dir/kernel-dummy.spec
install_changes $build_dir/kernel-dummy.changes

echo "Copying various files..."
cp -a                       \
    config.conf             \
    supported.conf          \
    rpm/*                   \
    scripts/guards          \
    scripts/arch-symbols    \
    doc/README.SUSE         \
    $build_dir
rm -f "$build_dir"/*spec.in "$build_dir"/get_release_number.sh.in \
    "$build_dir"/old-packages.conf "$build_dir"/km.conf \
    "$build_dir"/package-descriptions
# Not all files are in all branches
for f in misc/extract-modaliases scripts/kabi-checks; do
    if test -e "$f"; then
        cp -a "$f" "$build_dir"
    fi
done
if grep -q '^Source.*:[[:space:]]*log\.sh[[:space:]]*$' rpm/kernel-source.spec.in; then
	cp -p scripts/rpm-log.sh "$build_dir"/log.sh
fi

if [ -e extra-symbols ]; then
	install -m 755					\
		extra-symbols				\
		$build_dir
fi


if [ -x /work/src/bin/tools/convert_changes_to_rpm_changelog ]; then
    /work/src/bin/tools/convert_changes_to_rpm_changelog \
	"$build_dir"/kernel-source*.changes >"$build_dir"/rpm_changelog
    for spec in "$build_dir"/*.spec; do
        (echo "%changelog"; cat "$build_dir"/rpm_changelog) >>"$spec"
    done
    rm -f "$build_dir"/rpm_changelog
fi


if [ -n "$source_timestamp" ]; then
	ts="$(head -n 1 $build_dir/$tsfile)"
	branch=$(sed -nre 's/^(CVS|GIT) Branch: //p' \
		 $build_dir/$tsfile)
	rpm_release_string=${branch:-HEAD}_$(date --utc '+%Y%m%d%H%M%S' -d "$ts")
fi

sed -e "s:@RELEASE_PREFIX@:$RELEASE_PREFIX:"		\
    -e "s:@RELEASE_SUFFIX@:$rpm_release_string:"	\
    rpm/get_release_number.sh.in			\
    > $build_dir/get_release_number.sh
chmod 755 $build_dir/get_release_number.sh

# Usage:
# stable_tar [-t <timestamp>] [-C <dir>] [--exclude=...] <tarball> <files> ...
# if -t is not given, files must be within a git repository
stable_tar() {
    local tarball mtime chdir="." tar_opts=()

    while test $# -gt 2; do
        case "$1" in
        -t)
            mtime=$2
            shift 2
            ;;
        -C)
            chdir=$2
	    tar_opts=("${tar_opts[@]}" -C "$2")
            shift 2
            ;;
        --exclude=*)
            tar_opts=("${tar_opts[@]}" "$1")
            shift
            ;;
        --exclude)
            tar_opts=("${tar_opts[@]}" "$1" "$2")
            shift 2
            ;;
        *)
            break
        esac
    done
    tarball=$1
    shift

    if test -z "$mtime" && $using_git; then
	local dirs=$(printf '%s\n' "$@" | sed 's:/.*::' | sort -u)
        mtime="$(cd "$chdir"
            echo "${dirs[@]}" | xargs git log -1 --pretty=tformat:%ct -- | sort -n | \
            tail -n 1)"
    fi
    if test -n "$mtime"; then
        tar_opts=("${tar_opts[@]}" --mtime "$mtime")
    fi
    case "$IBS_PROJECT" in
    SUSE:SLE-9*)
        tar_opts=("${tar_opts[@]}" --no-paxheaders)
    esac
    printf '%s\n' "$@" | \
	    scripts/stable-tar.pl "${tar_opts[@]}" -T - >"${tarball%.bz2}" || exit
    bzip2 -9 "${tarball%.bz2}" || exit
}

# The first directory level determines the archive name
all_archives="$(
    echo "$referenced_files" \
    | sed -e 's,/.*,,' \
    | uniq )"
for archive in $all_archives; do
    echo "$archive.tar.bz2"

    files="$(echo "$referenced_files" | sed -ne "\:^${archive//./\\.}/:p")"
    if [ -n "$files" ]; then
	stable_tar $build_dir/$archive.tar.bz2 $files
    fi
done

if test -d kabi; then
    echo "kabi.tar.bz2"
    stable_tar $build_dir/kabi.tar.bz2 kabi
fi

for kmp in  novell-kmp hello; do
    if test ! -d "doc/$kmp"; then
        continue
    fi
    echo "$kmp.tar.bz2"
    stable_tar -C doc --exclude='*.o' --exclude='*.ko' --exclude='*.*.cmd' \
        "$build_dir/$kmp.tar.bz2" "$kmp"
done

# Create empty dummys for any *.tar.bz2 archive mentioned in the spec file
# not already created: patches.addon is empty by intention; others currently
# may contain no patches.
archives=$(sed -ne 's,^Source[0-9]*:.*[ \t/]\([^/]*\)\.tar\.bz2$,\1,p' \
           $build_dir/*.spec | sort -u)
for archive in $archives; do
    case "$archive" in
    *%*)
        # skip archive names with macros
        continue
    esac
    if test -e "$build_dir/$archive.tar.bz2"; then
        continue
    fi
    echo "$archive.tar.bz2 (empty)"
    tmpdir2=$(mktemp -dt ${0##*/}.XXXXXX)
    CLEANFILES=("${CLEANFILES[@]}" "$tmpdir2")
    mkdir -p $tmpdir2/$archive
    stable_tar -C $tmpdir2 -t 1234567890 $build_dir/$archive.tar.bz2 $archive
done

# Force mbuild to choose build hosts with enough memory available:
echo $((1024*1024)) > $build_dir/minmem
# Force mbuild to choose build hosts with enough disk space available:
echo $((6*1024)) > $build_dir/needed_space_in_mb
if [ -n "$ignore_kabi" ]; then
    echo > $build_dir/IGNORE-KABI-BADNESS
fi
if [ -n "$ignore_unsupported_deps" ]; then
    echo > $build_dir/IGNORE-UNSUPPORTED-DEPS
fi
