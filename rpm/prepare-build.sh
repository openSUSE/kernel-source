#!/bin/bash
# vim: syntax=sh
#set -x
set -e
test -f /.buildenv || exit 0
this_release=`rpm -q --qf %{RELEASE} kernel-dummy`
echo this_release $this_release
test -n "$this_release" || exit 1
shopt -s nullglob
for i in /usr/src/packages/SOURCES/*.spec; do
	sed -i -e '/^BuildRequires:/s@kernel-dummy@@g' \
	       -e '/^BuildRequires:[ \t]*$/d' \
	       -e "/^Release:/s@^.*@Release: $this_release@" $i
done
