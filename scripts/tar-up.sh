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

# if this is SLE11_BRANCH and earlier, hand over to scripts/tar-up-old.sh
if test ! -x rpm/mkspec; then
    exec ${0%.sh}-old.sh "$@"
fi

. ${0%/*}/wd-functions.sh

sort()
{
	LC_ALL=C command sort "$@"
}

tolerate_unknown_new_config_options=
ignore_kabi=
mkspec_args=()
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
      # obsolete
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
      # ignored, set %supported_modules_check in the spec instead
      shift
      ;;
    -rs|--release-string)
      case "$2" in
      *' '*)
        echo "$1 option argument must not contain spaces" >&2
        exit 1
      esac
      mkspec_args=("${mkspec_args[@]}" --release "$2")
      shift 2
      ;;
    -h|--help|-v|--version)
	cat <<EOF

${0##*/} perpares a 'kernel-source' package for submission into autobuild

these options are recognized:
    -nf                to proceed if a new unknown .config option is found during make oldconfig
    -u		       update generated files in an existing kernel-source dir
    -i                 ignore kabi failures
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

suffix=$(sed -rn 's/^Source0:.*\.(tar\.[a-z0-9]*)$/\1/p' rpm/kernel-source.spec.in)
# Dot files are skipped by intention, in order not to break osc working
# copies. The linux tarball is not deleted if it is already there
for f in "$build_dir"/*; do
	case "$f" in
	*/"linux-$SRCVERSION.$suffix")
		continue
	esac
	rm -f "$f"
done
mkdir -p "$build_dir"
echo "linux-$SRCVERSION.$suffix"
get_tarball "$SRCVERSION" "$suffix" "$build_dir"

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

SKIP_XEN=true
used_configs=$( $(dirname $0)/guards --prefix=config $( $(dirname $0)/arch-symbols --list) < config.conf )
for file in $used_configs; do
	case $file in
	config/*/xen | config/*/ec2 | config/*/pv)
		SKIP_XEN=false ;;
	esac
done

if $SKIP_XEN; then
	echo "[ Xen configs are disabled. Disabling Xen patches. ]"
	sed -i 's#.*patches.xen/#+noxen  &#' $build_dir/series.conf
fi

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

tsfile=source-timestamp
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

CLEANFILES=()
trap 'if test -n "$CLEANFILES"; then rm -rf "${CLEANFILES[@]}"; fi' EXIT
tmpdir=$(mktemp -dt ${0##*/}.XXXXXX)
CLEANFILES=("${CLEANFILES[@]}" "$tmpdir")

cp -p rpm/* config.conf supported.conf doc/* $build_dir
if test -e misc/extract-modaliases; then
	cp misc/extract-modaliases $build_dir
fi
# install this file only if the spec file references it
if grep -q '^Source.*:[[:space:]]*log\.sh[[:space:]]*$' rpm/kernel-source.spec.in; then
	cp -p scripts/rpm-log.sh "$build_dir"/log.sh
fi
rm -f "$build_dir/kernel-source.changes.old" "$build_dir/gitlog-fixups"
if test -e "$build_dir"/config-options.changes; then
	# Rename to  avoid triggering a build service rule error
	mv "$build_dir"/config-options.changes \
		"$build_dir"/config-options.changes.txt
fi
# FIXME: move config-subst out of rpm/
rm "$build_dir/config-subst"

changelog=$build_dir/kernel-source$VARIANT.changes
if test -e kernel-source.changes; then
    cat kernel-source.changes{,.old} >"$changelog"
elif $using_git; then
    exclude=()
    # Exclude commits in the scripts branch, these are rarely interesting for
    # users of the rpm packages.
    # FIXME: the remote might have a different name than "origin" or there
    # might be no remote at all.
    if git cat-file -e origin/scripts 2>/dev/null; then
        exclude[${#exclude[@]}]=^origin/scripts
    fi
    if git cat-file -e scripts 2>/dev/null; then
        exclude[${#exclude[@]}]=^scripts
    fi
    if test ${#exclude[@]} -eq 0; then
        echo "warning: no scripts or origin/scripts branch found" >&2
        echo "warning: rpm changelog will have some useless entries" >&2
    fi
    changes_stop=$(sed 1q rpm/kernel-source.changes.old)
    case "$changes_stop" in
    last\ commit:\ *)
        exclude[${#exclude[@]}]=^${changes_stop#*: }
        ;;
    *)
        echo "expected \"last commit: <commit>\" in rpm/kernel-source.changes.old" >&2
        exit 1
    esac
    if test -e rpm/gitlog-fixups; then
	    exclude=(--fixups "$_" "${exclude[@]}")
    fi
    scripts/gitlog2changes "${exclude[@]}" HEAD -- >"$changelog"
    sed 1d rpm/kernel-source.changes.old >>"$changelog"
    scripts/rpm-changes-merge.pl -1 "$changelog"
else
    touch "$changelog"
fi

if [ -e extra-symbols ]; then
	install -m 755					\
		extra-symbols				\
		$build_dir
fi

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

if test -d sysctl && \
	grep -q '^Source.*\<sysctl\.tar\.bz2' "$build_dir/kernel-source.spec.in"
then
	echo "sysctl.tar.bz2"
	stable_tar $build_dir/sysctl.tar.bz2 sysctl
fi


# Create empty dummys for any *.tar.bz2 archive mentioned in the spec file
# not already created: patches.addon is empty by intention; others currently
# may contain no patches.
archives=$(sed -ne 's,^Source[0-9]*:.*[ \t/]\([^/]*\)\.tar\.bz2$,\1,p' \
           $build_dir/kernel-source.spec.in | sort -u)
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
if [ -n "$tolerate_unknown_new_config_options" ]; then
    echo > $build_dir/TOLERATE-UNKNOWN-NEW-CONFIG-OPTIONS
fi

echo "cd $build_dir; ./mkspec ${mkspec_args[@]}"
patches=$PWD
cd "$build_dir"
./mkspec --patches "$patches" "${mkspec_args[@]}"
