#!/bin/sh

enable_x() {
	local enable=true
	while [ $# -gt 0 ] ; do
		{ [ "$1" = "-q" ] || [ "$1" = "--quiet" ] ; } && enable=false
		shift
	done
	$enable && set -x
	}

enable_x "$@"

testdir=$(dirname "$(readlink -f "$0")")
keys="Kernel.gpg"

for key in $keys ; do
	cp -a $testdir/../../lib/SUSE/$key $testdir/Docker
done

trap '
for key in $keys ; do
	rm $testdir/Docker/$key
done
' EXIT

for release in \
	sle12-sp4 \
	sle12-sp5 \
	sle15 \
	opensuse-15.4 \
	opensuse-tumbleweed \
	; do
	echo "Building container image for $release..."
	docker build "$@" -t gs-test-$release -f $testdir/Docker/$release.Dockerfile --build-arg release=$release $testdir/Docker
	ret=$?
	[ $ret -eq 0 ] || exit $ret
	echo "Running tests in $release:"
	docker run --rm --name=gs-test-$release \
		--mount type=bind,source="$testdir/../../",target=/scripts,readonly \
		gs-test-$release
	ret=$?
	[ $ret -eq 0 ] || exit $ret
done
