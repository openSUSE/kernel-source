#! /bin/bash

# log.sh - Automate insertion of patches into a kernel rpm tree managed
# with series.conf
#
# Usage example:
#
# osc branch openSUSE:11.3/kernel-source
# osc co home:philipsb:branches:openSUSE:11.3:Update:Test/kernel-source
# mv ~/linux-2.6/driver-fix-for-something.patch .
# echo -e "\tpatches.drivers/driver-fix-for-something.patch" >> series.conf
# ./log.sh
# osc commit

#############################################################################
# Copyright (c) 2004-2006,2008-2010 Novell, Inc.
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

# Construct a changes entry and commit log from a patch.

CHANGES=kernel-source.changes

trap 'rm -rf "$tmpdir"' EXIT
tmpdir=$(mktemp -d /tmp/${0##*/}.XXXXXX)
message=$tmpdir/message

log_entry() {
    local entry=$1

    echo "$entry" \
    | fmt --width 65 \
    | sed -e '1s/^/- /' -e '2,$s/^/  /' \
    >> $message
}


patch_meta() {
    local patch=$1

    subject=$(formail -c -x Subject < "$patch" \
             | sed -e 's, *\[[#/ A-Za-z0-9-]*\],,')
    subject=${subject## }
    subject=${subject%.}

    set -- $(formail -c -x References -x Reference < "$patch")
    references="$*"
}

patch_log_entry() {
    local patch=$1 subject references old_subj old_ref old_patch="$tmpdir/old"

    git show "HEAD:$patch" >"$old_patch" 2>/dev/null
    patch_meta "$old_patch"
    old_subj="$subject"
    old_ref="$references"

    patch_meta "$patch"

    local msg
    if test -z "$subject" -o "$subject" != "$old_subj"; then
        msg="$subject${references:+ ($references)}" 
    elif test "$references" != "$old_ref"; then
        if test -n "$references"; then
            msg="Update references ($references)"
        fi
    else
        msg="Refresh"
    fi

    log_entry "$patch: $msg${msg:+.}"
}

find_patches() {
       osc diff series.conf \
       | sed -n "s/^+\s*\(patches.*\)/\1/p"
}

for file in  "$@" $(find_patches); do
    dirname=$(dirname $file)
    basename=$(basename $file)
    archive=$dirname.tar.bz2

    if [ ! -f $basename ]; then
        echo "ERROR: $basename added to series.conf but doesn't exist in $PWD"
        exit 1
    fi

    if [ ! -d $dirname ]; then
        tar xvf $archive
    fi
    
    mv $basename $dirname
    rm $archive
    tar cfj $archive $dirname

    files[${#files[@]}]=$file
done 

if [ ${#files[@]} -eq 0 ]; then
    echo "No modified files" >&2
    exit 1
fi

for file in "${files[@]}"; do
    if [ "${file:0:1}" = - ]; then
	log_entry "${file:1}: Delete."
    else
	case "$file" in
	    config/*)
		if [ -z "$configs_updated" ]; then
		    log_entry "Update config files."
		    configs_updated=1
		fi
		;;
		
	    patches.*)
		patch_log_entry "$file"
		;;

	    kabi/*/symvers-* | kabi/*/symtypes-* | kabi/*/symsets-* )
		if [ -z "$symvers_updated" ]; then
		    log_entry "Update reference module symbol versions."
		    symvers_updated=1
		fi
	    	;;

	    series.conf)
		# don't log changes in there
		;;

	    *)
		log_entry "$file: "
		;;
	esac
    fi
done

if [ ! -s $message ]; then
    echo "- " >> $message
fi

if osc vc $CHANGES $message; then
    entry=$(sed -ne '1,2d' -e '/^--*$/!p' -e '/^--*$/q' $CHANGES)
    entry=${entry##$'\n'}
    entry=${entry%%$'\n'}
fi

for c in *.changes; do
    [ $c = $CHANGES ] && continue
    cp $CHANGES $c
done
