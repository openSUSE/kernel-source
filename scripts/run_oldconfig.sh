#!/bin/bash
set -x

case "$1" in
	y|-y|--yes)
	YES="yes '' | "
	;;
	*)
	YES=""
	;;
esac

for i in arch/*/defconfig.*
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
test -f patches/config/$A/$B && cp -v .config patches/config/$A/$B
diff -u $i .config
done
