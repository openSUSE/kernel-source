#!/bin/bash
set -x

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
for i in arch/$ARCH/defconfig.*
do
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
$YES make ARCH=$ARCH oldconfig
cp -v .config ${A}_$C
[ -f patches/config/$A/$B ] && cp -v .config patches/config/$A/$B
diff -U0 $i .config
done
