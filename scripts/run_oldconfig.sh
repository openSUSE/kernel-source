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

config_subst=${0%/*}/../rpm/config-subst

#########################################################
# dirty scroll region tricks ...

use_region=0

function _region_init_ () {
    echo -ne '\x1b[H\033[J'	# clear screen
    echo -ne '\x1b[4;0r'	# setup scroll region
    echo -ne '\x1b[4;0H'	# move cursor
}

function _region_fini_ () {
    echo -ne '\x1b7'		# save cursor
    echo -ne '\x1b[0;0r'		# del scroll region
    echo -ne '\x1b8'		# restore cursor
}

function _region_msg_ () {
    local msg="$*"
    if test "$use_region" != "0"; then
	echo -ne '\x1b7'	# save cursor
	echo -ne '\x1b[0;0H'	# move cursor
	echo -e "##\x1b[K"	# message
	echo -e "## $msg\x1b[K"	# message
	echo -e "##\x1b[K"	# message
	echo -ne '\x1b8'	# restore cursor
    else
	echo -e "##"
	echo -e "## $msg"
	echo -e "##"
    fi
}

set_var()
{
	local name=$1 val=$2 config config_files

	name="${name%%=*}"
	case "$name" in
		CONFIG_*) ;;
		*) name="CONFIG_$name" ;;
	esac
	config_files=$(${prefix}scripts/guards $CONFIG_SYMBOLS < ${prefix}config.conf)
	if [ -n "$set_flavor" ] ; then
		echo "appending $name=$val to all -$set_flavor config files listed in config.conf"
		config_files=$(printf "%s\n" $config_files | grep "/$set_flavor\$")
	else
		echo "appending $name=$val to all config files listed in config.conf"
	fi
	for config in $config_files; do
		if test -L "${prefix}config/$config"; then
			continue
		fi
		sed -i "/\\<$name[ =]/d" "${prefix}config/$config"
		case "$val" in
		y | m) echo "$name=$val" ;;
		n) echo "# $name is not set" ;;
		esac >> ${prefix}config/$config
	done
}


function _cleanup_() {
	test -d "$TMPDIR" && rm -rf $TMPDIR
	test "$use_region" != 0 && _region_fini_
}
TMPDIR=
trap _cleanup_ EXIT

#########################################################
# main

cpu_arch=
YES=
menuconfig=no
new_config_option_yes=no
new_config_option_mod=no
new_config_option_no=no
until [ "$#" = "0" ] ; do
    case "$1" in
    y|-y|--yes)
	YES="yes '' | "
	shift
	;;
    a|-a|--arch)
	cpu_arch=$2
	shift 2
	;;
    m|-m|--menuconfig)
	menuconfig=yes
	shift
	;;
    -nco-y|--new-config-option-yes)
	new_config_option_yes="$2"
	shift 2
	;;
    -nco-m|--new-config-option-mod)
	new_config_option_mod="$2"
	shift 2
	;;
    -nco-n|--new-config-option-no|-dco|--disable-config-option)
	new_config_option_no="$2"
	shift 2
	;;
    --flavor)
	set_flavor="$2"
	shift 2
	;;
    --vanilla)
	set_flavor="vanilla"
	shift
	;;
    -h|--help)
	cat <<EOF

${0##*/} does either:
 * run make oldconfig to clean up the .config files
 * modify kernel .config files in the CVS tree

run it with no options in your SCRATCH_AREA $SCRATCH_AREA, like
	patches/scripts/${0##*/}
possible options in this mode:
	called with no option will run just make oldconfig interactive
	y|-y|--yes         to run 'yes "" | make oldconfig'
	a|-a|--arch        to run make oldconfig only for the given arch
	m|-m|--menuconfig  to run make menuconfig instead of oldconfig
	--flavor <flavor>  to run only for configs of specified flavor
	--vanilla          an alias for "--flavor vanilla"

run it with one of the following options to modify all .config files listed
in config.conf:
	-nco-y|--new-config-option-yes   compile something into the kernel
	-nco-m|--new-config-option-mod   compile something as a module
	-nco-n|--new-config-option-no    disable a kernel .config option
	-dco|--disable-config-option     alias for -nco-n
each of them takes a second argument, which can be either
FOO
FOO=X
CONFIG_FOO
CONFIG_FOO=X
EOF
	exit 1
	;;
    *)
	echo ugh
    	exit 1
	;;
    esac
done

if [ -f patches/scripts/arch-symbols ] ; then
	prefix=patches/
elif [ -f scripts/arch-symbols ] ; then
	prefix=
else
	echo "no arch-symbols found"
	exit 1
fi

if [ -z "$cpu_arch" ]; then
    CONFIG_SYMBOLS=$(
        for arch in $(${prefix}scripts/arch-symbols --list); do
            ${prefix}scripts/arch-symbols $arch
        done
    )
else
    CONFIG_SYMBOLS=$(${prefix}scripts/arch-symbols $cpu_arch)
fi

if [ "$new_config_option_yes" != "no" ] ; then
	set_var "$new_config_option_yes" y
	exit 0
fi
if [ "$new_config_option_mod" != "no" ] ; then
	set_var "$new_config_option_mod" m
	exit 0
fi
if [ "$new_config_option_no" != "no" ] ; then
	set_var "$new_config_option_no" n
	exit 0
fi

if [ "$menuconfig" = "no" ] ; then
	case "$TERM" in
	linux* | xterm* | screen*)
	    use_region=1
	    _region_init_
	    ;;
	esac
fi

config_files=$(${prefix}scripts/guards $CONFIG_SYMBOLS < ${prefix}config.conf)

if [ -z "$set_flavor" ] ; then
    config_files=$(printf "%s\n" $config_files | grep -v vanilla)
else
    config_files=$(printf "%s\n" $config_files | grep "/$set_flavor\$")
fi

TMPDIR=$(mktemp -td ${0##*/}.XXXXXX)

EXTRA_SYMBOLS=
if [ -s extra-symbols ]; then
    EXTRA_SYMBOLS="$(cat extra-symbols)"
fi

${prefix}scripts/guards $EXTRA_SYMBOLS < ${prefix}series.conf \
    > $TMPDIR/applied-patches

EXTRA_SYMBOLS="$(echo $EXTRA_SYMBOLS | sed -e 's# *[Rr][Tt] *##g')"

last_arch=

for config in $config_files; do
    cpu_arch=${config%/*}
    flavor=${config#*/}

    if test -L "${prefix}config/$config"; then
        continue
    fi
    set -- kernel-$flavor $flavor $(case $flavor in (rt|rt_*) echo RT ;; esac)
    ${prefix}scripts/guards $* $EXTRA_SYMBOLS \
	< ${prefix}series.conf > $TMPDIR/patches

    if ! diff -q $TMPDIR/applied-patches $TMPDIR/patches > /dev/null; then
	echo "Not all patches for $config are applied; skipping"
	diff -u $TMPDIR/applied-patches $TMPDIR/patches
	continue
    fi

    case $cpu_arch in
	ppc|ppc64) kbuild_arch=powerpc ;;
	s390x) kbuild_arch=s390 ;;
	*) kbuild_arch=$cpu_arch ;;
    esac
    MAKE_ARGS="ARCH=$kbuild_arch"
    config="${prefix}config/$config"

    cat $config \
    | bash $config_subst CONFIG_LOCALVERSION \"-${config##*/}\" \
    | bash $config_subst CONFIG_SUSE_KERNEL y \
    > .config
    case "$menuconfig" in
    yes)
	KCONFIG_NOTIMESTAMP=1 make $MAKE_ARGS menuconfig
	;;
    *)
	_region_msg_ "working on $config"
	eval $YES KCONFIG_NOTIMESTAMP=1 make $MAKE_ARGS oldconfig
	;;
    esac
    if ! diff -U0 $config .config; then
	sed '/^# Linux kernel version:/d' < .config > $config
    fi
done
