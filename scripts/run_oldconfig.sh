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

#########################################################
# dirty scroll region tricks ...

use_region=false

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
    if $silent; then
	    return
    fi
    if $use_region; then
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

info()
{
	if $silent; then
		return
	fi
	echo "$@"
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
		info "appending $name=$val to all -$set_flavor config files listed in config.conf"
		config_files=$(printf "%s\n" $config_files | grep "/$set_flavor\$")
	else
		info "appending $name=$val to all config files listed in config.conf"
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
	if $use_region; then
		_region_fini_
	fi
}
TMPDIR=
trap _cleanup_ EXIT

#########################################################
# main

cpu_arch=
mode=oldconfig
option=
value=
silent=false
check=false
until [ "$#" = "0" ] ; do
	case "$1" in
	y|-y|--yes)
		mode=yes
		shift
		;;
	--mod)
		mode=allmodconfig
		shift
		;;
	a|-a|--arch)
		cpu_arch=$2
		shift 2
		;;
	m|-m|--menuconfig)
		mode=menuconfig
		shift
		;;
	-nco-y|--new-config-option-yes)
		mode=single
		option=$2
		value=y
		shift 2
		;;
	-nco-m|--new-config-option-mod)
		mode=single
		option=$2
		value=m
		shift 2
		;;
	-nco-n|--new-config-option-no|-dco|--disable-config-option)
		mode=single
		option=$2
		value=n
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
	--check)
		check=true
		shift
		;;
	-s|--silent)
		silent=true
		shift
		;;
	-h|--help)
		cat <<EOF

${0##*/} does either:
 * run make oldconfig to clean up the .config files
 * modify kernel .config files in the GIT tree

run it with no options in your SCRATCH_AREA $SCRATCH_AREA, like
	patches/scripts/${0##*/}
possible options in this mode:
	called with no option will run just make oldconfig interactive
	y|-y|--yes         to run 'yes "" | make oldconfig'
	--mod              to set all new options to 'm' (booleans to 'y')
	a|-a|--arch        to run make oldconfig only for the given arch
	m|-m|--menuconfig  to run make menuconfig instead of oldconfig
	--flavor <flavor>  to run only for configs of specified flavor
	--vanilla          an alias for "--flavor vanilla"
	--check            just check if configs are up to date

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

Run with -s|--silent in both modes to suppress most output
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

if test -e "${prefix}rpm/config.sh"; then
	source "$_"
fi
if test -z "$set_flavor" && test "$VANILLA_ONLY" = 1 -o -e .is_vanilla; then
	set_flavor=vanilla
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

case "$mode" in
single)
	set_var "$option" "$value"
	exit 0
	;;
menuconfig)
	;;
*)
	case "$TERM" in
	linux* | xterm* | screen*)
		if tty -s && ! $silent; then
			use_region=true
			_region_init_
		fi
	esac
esac

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

mkdir $TMPDIR/reuse

ask_reuse_config()
{
    local old=$1 new=$2

    # if the user either asked to never reuse the config or if this config
    # already reused something, do nothing
    for f in $TMPDIR/reuse/{never,all,$cpu_arch-all,all-$flavor}; do
        if test -e "$f"; then
            return
        fi
    done
    diff $old $new | awk >$TMPDIR/reuse/diff '
        /< .*CONFIG_/ { x[substr($0, 3)]--; }
        /> .*CONFIG_/ { x[substr($0, 3)]++; }
        END {
            for (l in x)
                if (x[l] > 0)
                    print l;
        }'

    if test ! -s $TMPDIR/reuse/diff; then
        return
    fi
    while :; do
        echo
        cat $TMPDIR/reuse/diff | sed 's/^/  /'
        echo
        echo "Use these settings for other configurations?"
        read -p "[Y]es/for [A]rch $cpu_arch/for [F]lavor $flavor/[N]o/[E]dit/ne[V]er "
        case "$REPLY" in
        [Yy] | "")
            mv $TMPDIR/reuse/diff $TMPDIR/reuse/all
            break ;;
        [Aa])
            mv $TMPDIR/reuse/diff $TMPDIR/reuse/$cpu_arch-all
            break ;;
        [Ff])
            mv $TMPDIR/reuse/diff $TMPDIR/reuse/all-$flavor
            break ;;
        [Ee])
            ${VISUAL:-${EDITOR:-vi}} $TMPDIR/reuse/diff
            ;;
        [Nn])
            rm $TMPDIR/reuse/diff
            break ;;
        [Vv])
            rm $TMPDIR/reuse/diff
                touch $TMPDIR/reuse/never
            break ;;
        esac
    done
}

filter_config()
{
    sed -e '/^# .* is not set$/p' -e '/^$\|^#/d' "$@" | sort
}

err=0
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

    case $config in
    ppc*/*)
        if test -e arch/powerpc/Makefile; then
            MAKE_ARGS="ARCH=powerpc"
        else
            MAKE_ARGS="ARCH=$cpu_arch"
        fi
        ;;
    s390x/*)
        MAKE_ARGS="ARCH=s390"
        ;;
    arm64/*)
        MAKE_ARGS="ARCH=arm64"
        ;;
    armv*/*)
        MAKE_ARGS="ARCH=arm"
        ;;
    */um)
        MAKE_ARGS="ARCH=um SUBARCH=$cpu_arch"
        ;;
    *)
        MAKE_ARGS="ARCH=$cpu_arch"
        ;;
    esac
    if $silent; then
	    MAKE_ARGS="$MAKE_ARGS -s"
    fi
    config="${prefix}config/$config"

    cat $config | \
    if grep -qw CONFIG_CFGNAME "$config"; then
        # SLES9
        cat
    else
        bash ${prefix}rpm/config-subst CONFIG_LOCALVERSION \"-$flavor\"
    fi \
    | bash ${prefix}rpm/config-subst CONFIG_SUSE_KERNEL y \
    > .config
    for f in $TMPDIR/reuse/{all,$cpu_arch-all,all-$flavor}; do
        if test -e "$f"; then
            info "Reusing choice for ${f##*/}"
            cat "$f" >>.config
        fi
    done
    export KCONFIG_NOTIMESTAMP=1
    case "$mode" in
    menuconfig)
	make $MAKE_ARGS menuconfig
	;;
    yes)
	_region_msg_ "working on $config"
	yes '' | make $MAKE_ARGS oldconfig
	touch $TMPDIR/reuse/never
	;;
    allmodconfig)
	_region_msg_ "working on $config"
	cp .config config-old
	KCONFIG_ALLCONFIG=config-old make $MAKE_ARGS allmodconfig
	rm config-old
	touch $TMPDIR/reuse/never
	;;
    *)
	_region_msg_ "working on $config"
        if $check; then
            if ! make $MAKE_ARGS silentoldconfig </dev/null; then
                echo "${config#$prefix} is out of date"
                err=1
                continue
            fi
        else
            make $MAKE_ARGS oldconfig
        fi
    esac
    if ! $check; then
        ask_reuse_config $config .config
        if ! $silent; then
            diff -U0 $config .config
        fi
        cp .config $config
        continue
    fi
    differences="$(
        diff -bU0 <(filter_config "$config") <(filter_config .config) | \
        grep '^[-+][^-+]'
    )"
    if echo "$differences" | grep -q '^+' ; then
        echo "Changes in ${config#$prefix} after running make oldconfig:"
        echo "$differences"
        err=1
    fi
done

exit $err
