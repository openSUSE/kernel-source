#!/bin/bash
#set -x

#########################################################
# dirty scroll region tricks ...

use_region=0

function _region_init_ () {
    echo -e '\x1b[H\033[J'		# clear screen
    echo -e '\x1b[4;0r'		# setup scroll region
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
	echo -ne '\x1b[0;0H'	# move cursoe
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

case "$TERM" in
linux | xterm | screen)
    use_region=1
    _region_init_
    trap "_region_fini_" EXIT
    ;;
esac

cvs_wd=$(readlink patches)

#########################################################
# main

arch="--list"
YES=
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
    *)
	shift
	;;
    esac
done
for config in $(cd $cvs_wd && \
	        eval scripts/guards $arch < config.conf); do
    arch=${config%/*}
    flavor=${config#*/}
    case $flavor in
    um)
	MAKE_ARGS="ARCH=um SUBARCH=$arch"
	;;
    *)
	MAKE_ARGS="ARCH=$arch"
	;;
    esac
    config="patches/config/$config"

    _region_msg_ "working on $config"
    cp -v $config .config
    eval $YES make $MAKE_ARGS oldconfig
    if ! diff -U0 $config .config; then
	cp -v .config $config
	cp -v .config arch/$arch/defconfig.$flavor
    fi
done
