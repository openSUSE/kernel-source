#!/bin/bash

. ${0%/*}/wd-functions.sh

tolerate_unknown_new_config_options=
ignore_kabi=
mkspec_args=()
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

# dot files are skipped by intention, in order not to break osc working
# copies
rm -f $build_dir/*
mkdir -p $build_dir

# generate the list of patches to include.
if [ -n "$embargo_filter" ]; then
    scripts/embargo-filter < series.conf > $build_dir/series.conf \
	|| exit 1
    chmod 644 $build_dir/series.conf
else
    install -m 644 series.conf $build_dir/
fi

# All config files and patches used
referenced_files="$( {
	$(dirname $0)/guards --list < $build_dir/series.conf
	$(dirname $0)/guards --prefix=config --list < config.conf
    } | sort -u )"

inconsistent=false
check_for_merge_conflicts $referenced_files kernel-source.changes{,.old} || \
	inconsistent=true
scripts/check-conf || inconsistent=true
scripts/check-cvs-add --committed || inconsistent=true
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

EXTRA_SYMBOLS=$([ -e extra-symbols ] && cat extra-symbols)


echo "Copying various files..."
install -m 644					\
	config.conf				\
	supported.conf				\
	rpm/config.sh                           \
	rpm/old-packages.conf                   \
	rpm/kernel-{binary,source,syms}.spec.in \
	rpm/devel-pre.sh			\
	rpm/devel-post.sh			\
	rpm/source-post.sh		        \
	rpm/{pre,post,preun,postun}.sh		\
	rpm/module-renames			\
	rpm/kernel-module-subpackage		\
	rpm/macros.kernel-source		\
	rpm/package-descriptions                \
	doc/README.SUSE				\
	doc/README.KSYMS			\
	$build_dir

install -m 755					\
	rpm/mkspec                              \
	rpm/find-provides			\
	rpm/config-subst 			\
	rpm/check-for-config-changes		\
	rpm/check-supported-list		\
	rpm/check-build.sh			\
	rpm/modversions				\
	rpm/built-in-where			\
	rpm/symsets.pl                          \
	rpm/split-modules                       \
	scripts/guards				\
	scripts/arch-symbols			\
	misc/extract-modaliases			\
	rpm/compute-PATCHVERSION.sh             \
	$build_dir

cat kernel-source.changes{,.old} > "$build_dir/kernel-source$VARIANT.changes"
install -m 644 rpm/kernel-source.rpmlintrc \
	"$build_dir/kernel-source$VARIANT.rpmlintrc"

if [ -e extra-symbols ]; then
	install -m 755					\
		extra-symbols				\
		$build_dir
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

# Usage:
# stable_tar [-t <timestamp>] [-C <dir>] [--exclude=...] <tarball> <files> ...
# if -t is not given, files must be within a git repository
tar_override_works=
stable_tar() {
    local tarball mtime=() chdir="." tar_opts=()

    while test $# -gt 2; do
        case "$1" in
        -t)
            mtime=(--mtime "$2")
            shift 2
            ;;
        -C)
            chdir=$2
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

    if [ -z "$tar_override_works" ]; then
        if tar --mtime="Tue, 3 Feb 2009 10:52:55 +0100" --owner=nobody \
                    --group=nobody --help >/dev/null; then
            tar_override_works=true
        else
            echo "warning: created tarballs will differ between runs" >&2
            tar_override_works=false
        fi
    fi
    if $tar_override_works; then
        if test -z "$mtime" && $using_git; then
            mtime=(--mtime "$(cd "$chdir"; git log --pretty=format:%cD "$@" | head -n 1)")
        fi
        tar_opts=("${tar_opts[@]}" --owner=nobody --group=nobody "${mtime[@]}")
    fi
    (
        cd "$chdir"
        find "$@" \( -type f -o -type d -a -empty \) -print0 | \
            LC_ALL=C sort -z | \
            tar cf - --null -T - "${tar_opts[@]}"
    ) | bzip2 -9 >"$tarball"
}

# The first directory level determines the archive name
all_archives="$(
    echo "$referenced_files" \
    | sed -e 's,/.*,,' \
    | uniq )"
for archive in $all_archives; do
    echo "$archive.tar.bz2"
    case " $IGNORE_ARCHS " in
    *" ${archive#patches.} "*)
	echo "Ignoring $archive..."
	continue ;;
    esac

    files="$( echo "$referenced_files" \
	| sed -ne "\:^${archive//./\\.}/:p" \
	| while read patch; do
	    [ -e "$patch" ] && echo "$patch"
	done)"
    if [ -n "$files" ]; then
	stable_tar $build_dir/$archive.tar.bz2 $files
    fi
done

echo "kabi.tar.bz2"
stable_tar $build_dir/kabi.tar.bz2 kabi

# Create empty dummys for any *.tar.bz2 archive mentioned in the spec file
# not already created: patches.addon is empty by intention; others currently
# may contain no patches.
archives=$(sed -ne 's,^Source[0-9]*:.*[ \t/]\([^/]*\)\.tar\.bz2$,\1,p' \
           $build_dir/kernel-binary.spec.in | sort -u)
for archive in $archives; do
    [ "$archive" = "linux-%srcversion" ] && continue
    if ! [ -e $build_dir/$archive.tar.bz2 ]; then
	echo "$archive.tar.bz2 (empty)"
	tmpdir2=$(mktemp -dt ${0##*/}.XXXXXX)
	CLEANFILES=("${CLEANFILES[@]}" "$tmpdir2")
	mkdir -p $tmpdir2/$archive
	stable_tar -C $tmpdir2 -t "Wed, 01 Apr 2009 12:00:00 +0200" \
	    $build_dir/$archive.tar.bz2 $archive
    fi
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
