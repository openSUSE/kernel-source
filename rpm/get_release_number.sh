#! /bin/sh

r=`rpm -q --qf %{RELEASE}\\\n kernel-dummy`
if test "$?" = 0
then
	echo "$r"
else
	echo "pkg:kernel-dummy"
fi
