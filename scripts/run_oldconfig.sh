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

#########################################################
# main

ARCH="*"
until [ "$#" = "0" ] ; do
  case "$1" in
    y|-y|--yes)
      YES="yes '' | "
      shift
      ;;
    a|-a|--arch)
      shift
      if [ -d arch/$1 -a "$1" != "" ] ; then
	ARCH=$1
	shift
	echo running make oldconfig only for arch $ARCH
      else
	echo "$1 is not a valid directory in arch/"
	exit
      fi
      ;;
    *)
      YES=""
      shift
      ;;
  esac
done
for i in arch/$ARCH/defconfig.*; do
  #
  A=${i#*/}
  A=${A%%/*}
  C=${i##*/}
  B=${C#*.}
  #
  case "$i" in
    *.um)
      ARCH=um
      ;;
    *)
      ARCH=$A
      ;;
  esac
  echo $A ${A}_$C
  cp -v $i .config
#  echo working on $i, press RETURN
#  read
  _region_msg_ "working on $i"
  eval $YES make ARCH=$ARCH oldconfig
  cp -v .config ${A}_$C
  if [ -f patches/config/$A/$B ] \
     && ! diff -q .config patches/config/$A/$B ; then
	  cp -v .config patches/config/$A/$B
  fi
  diff -U0 $i .config
done
