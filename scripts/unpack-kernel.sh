#!/bin/sh
#############################################################################
# Copyright (c) 2006 Novell, Inc.
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
#
# Thu Jul 13 19:14:04 EDT 2006 jeffm
#
# This script assembles a vanilla kernel tree from a combination of patches,
# tarballs, and existing directories. It uses the same MIRROR and SCRATCH_AREA
# variables as the rest of the CVS scripts.
#
# usage: unpack-kernel.sh <version>
#

function test_exists () {
    [ -e "$MIRROR/$1" -o -e "$MIRROR/$1.gz" -o -e "$MIRROR/$1.bz2" ]
}

function unpack () {
    echo "Unpacking $1 tarball"
    if [ -e "$MIRROR/$1" ]; then
        tar xf "$MIRROR/$1" --directory "$SCRATCH_AREA"
    elif [ -e "$MIRROR/$1.gz" ]; then
        tar zxf "$MIRROR/$1.gz" --directory "$SCRATCH_AREA"
    elif [ -e "$MIRROR/$1.bz2" ]; then
        tar jxf "$MIRROR/$1.bz2" --directory "$SCRATCH_AREA"
    else
        echo "Cannot unpack $1 - no such file."
        exit 1
    fi
}

function trypatch () {
    echo "Patching with $1"
    if [ -e "$MIRROR/$1" ]; then
       patch -p1 -s -d "$SCRATCH_AREA/$DIR" < "$MIRROR/$1"
    elif [ -e "$MIRROR/$1.gz" ]; then
       zcat "$MIRROR/$1.gz" | patch -p1 -s -d "$SCRATCH_AREA/$DIR"
    elif [ -e "$MIRROR/$1.bz2" ]; then
       bzcat "$MIRROR/$1.bz2" | patch -p1 -s -d "$SCRATCH_AREA/$DIR"
    else
        echo "Cannot patch with $1 - no such file."
        exit 1
    fi

}

function _unpack_kernel () {
    if [ $# -lt 2 ]; then
        echo "usage: $0 <unpack> <version> [dir: defaults to linux-\$version]"
        return 1
    fi

    UNPACK=$1
    VERSION=$2
    DIR=$3

    if [ -z "$DIR" ]; then
        DIR=linux-$VERSION
    fi

    if [ -d "$SCRATCH_AREA/linux-$VERSION.orig" ]; then
        echo "$SCRATCH_AREA/linux-$VERSION.orig already exists."
        return 1
    fi

    if [ -z "$MIRROR" ]; then MIRROR=. ; fi

    MAJOR=`echo $VERSION|cut -d . -f 1`
    MINOR=`echo $VERSION|cut -d . -f 2`
    PATCH=`echo $VERSION|cut -d . -f 3|sed -e 's/[^0-9].*//'`
    NPATCH=$PATCH
    PATCH_EXTRA=`echo $VERSION|cut -d . -f 3|sed -e 's/^[0-9]*//'`
    EXTRA=`echo $VERSION|cut -d . -f 4`

    if [ -n "$EXTRA" ]; then
        if test_exists "patch-$VERSION"; then
            echo "$VERSION (patch)"
        elif test_exists "linux-$VERSION.tar"; then
            echo "$VERSION (tarball)"
            BASE_VERSION="$VERSION"
        else
            echo "$VERSION (missing)"
            MISSING=1
        fi
    fi

    if [ -n "$PATCH_EXTRA" ]; then
            if test_exists "patch-$MAJOR.$MINOR.$PATCH$PATCH_EXTRA"; then
                echo "$MAJOR.$MINOR.$PATCH$PATCH_EXTRA (patch)"
            elif test_exists "linux-$MAJOR.$MINOR.$PATCH$PATCH_EXTRA"; then
                echo "$MAJOR.$MINOR.$PATCH$PATCH_EXTRA (tarball)"
                BASE_VERSION="$MAJOR.$MINOR.$PATCH$PATCH_EXTRA"
            else
                echo "$MAJOR.$MINOR.$PATCH$PATCH_EXTRA (missing)"
                MISSING=1
            fi
            let NPATCH--
    fi

    for pl in `seq $NPATCH -1 0`; do
        if [ -d "$SCRATCH_AREA/linux-$MAJOR.$MINOR.$pl.orig" ]; then
            echo "$MAJOR.$MINOR.$pl (dir)"
            BASE_VERSION="$MAJOR.$MINOR.$pl"
            TARBALL=$pl
            DIREXISTS=1
            break;
        elif test_exists "linux-$MAJOR.$MINOR.$pl.tar"; then
            echo "$MAJOR.$MINOR.$pl (tarball)"
            BASE_VERSION="$MAJOR.$MINOR.$pl"
            TARBALL=$pl
            break;
        elif test_exists "patch-$MAJOR.$MINOR.$pl"; then
            echo "$MAJOR.$MINOR.$pl (patch)"
        else
            echo "$MAJOR.$MINOR.$pl (missing)"
            MISSING=1
        fi
    done

    if [ -n "$MISSING" ]; then
        echo ""
        echo "Cannot complete patch chain. Exiting."
        return 1
    fi

    if [ "$UNPACK" -ne "1" ]; then return 0; fi

    # If we can use an old directory, use it
    if [ -n "$DIREXISTS" ]; then
        cp -la "$SCRATCH_AREA/linux-$MAJOR.$MINOR.$TARBALL.orig" "$SCRATCH_AREA/$DIR"
    else
        unpack "linux-$BASE_VERSION.tar"
        if [ "$BASE_VERSION" != "$VERSION" ]; then
            mv -f "$SCRATCH_AREA/linux-$MAJOR.$MINOR.$TARBALL" "$SCRATCH_AREA/$DIR"
        fi
    fi

    let TARBALL++

    for pl in `seq $TARBALL $PATCH`; do
        trypatch "patch-$MAJOR.$MINOR.$pl"
    done

    if [ -n "$PATCH_EXTRA" -a "$BASE_VERSION" != "$MAJOR.$MINOR.$PATCH$PATCH_EXTRA" ]; then
        trypatch "patch-$MAJOR.$MINOR.$PATCH$PATCH_EXTRA"
    fi

    if [ -n "$EXTRA" -a "$BASE_VERSION" != "$VERSION" ]; then
        trypatch "patch-$VERSION"
    fi
}

function check_patch_chain () {
    _unpack_kernel 0 $@
}

function unpack_kernel () {
    _unpack_kernel 1 $@
}

if [ "`basename $0`" = "unpack-kernel.sh" ]; then
    unpack_kernel $@
fi
