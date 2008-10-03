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
	echo -e "##"
	echo -e "## $msg"
	echo -e "##"
    fi
}

function expand_config_option () {
	local opt="$1"
	opt="${opt%%=*}"
	case "$opt" in
		CONFIG_*) ;;
		*) opt="CONFIG_$opt" ;;
	esac
	echo "$opt"
}

function _cleanup_() {
	test -d "$TMPDIR" && rm -rf $TMPDIR
	test "$use_region" != 0 && _region_fini_
}
TMPDIR=
trap _cleanup_ EXIT

#########################################################
# main

arch=
YES=
menuconfig=no
new_config_option_yes=no
new_config_option_mod=no
new_config_option_no=no
vanilla=no
until [ "$#" = "0" ] ; do
    case "$1" in
    y|-y|--yes)
	YES="yes '' | "
	shift
	;;
    a|-a|--arch)
	arch=$2
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
    --vanilla)
	vanilla=yes
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
	--vanilla          to run make oldconfig only for the vanilla configs

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

if [ -z "$arch" ]; then
    CONFIG_SYMBOLS=$(
    	for arch in $(${prefix}scripts/arch-symbols --list); do
		${prefix}scripts/arch-symbols $arch
	done)
else
    ARCH_SYMBOLS=$(${prefix}scripts/arch-symbols $arch)
    CONFIG_SYMBOLS=$ARCH_SYMBOLS
fi

if [ "$new_config_option_yes" != "no" ] ; then
	new_config_option_yes="`expand_config_option $new_config_option_yes`"
	echo "appending $new_config_option_yes to all config files listed in config.conf"
	for config in $(scripts/guards $CONFIG_SYMBOLS < config.conf); do
		sed -i "/${new_config_option_yes}[ =]/d" config/$config
		# '"
		echo "${new_config_option_yes}=y" >> config/$config
	done
	exit 0
fi
if [ "$new_config_option_mod" != "no" ] ; then
	new_config_option_mod="`expand_config_option $new_config_option_mod`"
	echo "appending $new_config_option_mod to all config files listed in config.conf"
	for config in $(scripts/guards $CONFIG_SYMBOLS < config.conf); do
		sed -i "/${new_config_option_mod}[ =]/d" config/$config
		# '"
		echo "${new_config_option_mod}=m" >> config/$config
	done
	exit 0
fi
if [ "$new_config_option_no" != "no" ] ; then
	new_config_option_no="`expand_config_option $new_config_option_no`"
	echo "disable $new_config_option_no in all config files listed in config.conf"
	for config in $(scripts/guards $CONFIG_SYMBOLS < config.conf); do
		sed -i "/${new_config_option_no}[ =]/d" config/$config
		# '"
		echo "# ${new_config_option_no} is not set" >> config/$config
	done
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

config_files=$(patches/scripts/guards $CONFIG_SYMBOLS < patches/config.conf)

if [ "$vanilla" = "no" ] ; then
    config_files=$(printf "%s\n" $config_files | grep -v vanilla)
else
    config_files=$(printf "%s\n" $config_files | grep vanilla)
fi

TMPDIR=$(mktemp -td ${0##*/}.XXXXXX)

EXTRA_SYMBOLS=
if [ -s extra-symbols ]; then
    EXTRA_SYMBOLS="$(cat extra-symbols)"
fi

patches/scripts/guards $ARCH_SYMBOLS $EXTRA_SYMBOLS < patches/series.conf \
    > $TMPDIR/applied-patches

EXTRA_SYMBOLS="$(echo $EXTRA_SYMBOLS | sed -e 's# *[Rr][Tt] *##g')"

for config in $config_files; do
    arch=${config%/*}
    flavor=${config#*/}

    set -- kernel-$flavor $flavor $(case $flavor in (rt|rt_*) echo RT ;; esac)
    patches/scripts/guards $* $ARCH_SYMBOLS $EXTRA_SYMBOLS \
	< patches/series.conf > $TMPDIR/patches

    if ! diff -q $TMPDIR/applied-patches $TMPDIR/patches > /dev/null; then
	echo "Not all patches for $config are applied; skipping"
	diff -u $TMPDIR/applied-patches $TMPDIR/patches
	continue
    fi

    case $flavor in
    um)
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
    fi
done
