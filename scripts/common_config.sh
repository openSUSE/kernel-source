#!/bin/bash

#############################################################################
# Copyright (c) 2011 SUSE
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

# we try to find config options that are the same in all
# configs we pass as parameters

if [ ! "$1" ]; then
    echo "Common config checker"
    echo
    echo "Allows for new architectures to find out which options"
    echo "are generic SUSE options so we can set them too."
    echo
    echo "Usage: $0 <config> <config> ..."
    exit 1
fi

TMPFILE=/tmp/common_tmp.$$
sort "$@" | uniq -d -c > $TMPFILE
CONF_NR="$#"

while read COUNT LINE OPTION_NO; do
    if [ "${LINE:0:7}" = "CONFIG_" ]; then
        OPTION=$(echo $LINE | cut -d = -f 1)
    elif [ "${OPTION_NO:0:7}" = "CONFIG_" ]; then
        OPTION=$OPTION_NO
    else
        continue
    fi
    if [ "$COUNT" = "$CONF_NR" ]; then
        echo "$LINE" "$OPTION_NO"
    fi
done < $TMPFILE
