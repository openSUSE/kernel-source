#!/bin/bash
# vim: syntax=sh
#set -x
set -e
test -f /.buildenv || exit 0
this_release=`rpm -q --qf %{RELEASE} kernel-dummy`
echo this_release $this_release
test -z "$this_release" && exit 1
for i in /usr/src/packages/SOURCES/*.spec
do
	test -f $i || continue
	sed -e '/^BuildRequires:/s@kernel-dummy@@g' -e "/^Release:/s@^.*@Release: $this_release@" < $i > $i.$$
	mv -v $i.$$ $i
done
