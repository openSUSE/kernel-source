#!/bin/bash
#set -x

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
	echo -ne "##"
	echo -ne "## $msg"
	echo -ne "##"
    fi
}

#########################################################
# main

arch="--list"
YES=
menuconfig=no
until [ "$#" = "0" ] ; do
    case "$1" in
    y|-y|--yes)
	YES="yes '' | "
	shift
	;;
    a|-a|--arch)
	arch='$(scripts/arch-symbols '"$2"')'
	shift 2
	;;
    m|-m|--menuconfig)
	menuconfig=yes
	shift
	;;
    *)
	shift
	;;
    esac
done
if [ "$menuconfig" = "no" ] ; then
	case "$TERM" in
	linux | xterm | screen)
	    use_region=1
	    _region_init_
	    trap "_region_fini_" EXIT
	    ;;
	esac
fi

for config in $(cd patches && \
	        eval scripts/guards $arch < config.conf); do
    arch=${config%/*}
    flavor=${config#*/}
    case $flavor in
    um|xen)
	MAKE_ARGS="ARCH=$flavor SUBARCH=$arch"
	;;
    *)
	MAKE_ARGS="ARCH=$arch"
	;;
    esac
    config="patches/config/$config"

    cat $config \
    | $config_subst CONFIG_LOCALVERSION \"-${config##*/}\" \
    | $config_subst CONFIG_SUSE_KERNEL y \
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
	cp -v .config arch/$arch/defconfig.$flavor
    fi
done
