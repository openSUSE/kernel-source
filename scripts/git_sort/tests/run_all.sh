#!/bin/bash

libdir=$(dirname "$(readlink -f "$0")")

for release in \
	sle12-sp4 \
	sle12-sp5 \
	sle15 \
	opensuse-15.3 \
	opensuse-tumbleweed \
	; do
	echo "Building container image for $release..."
	docker build -q -t gs-test-$release "$libdir/$release"
	echo "Running tests in $release:"
	docker run --rm --name=gs-test-$release \
		--mount type=bind,source="$libdir/../../",target=/scripts,readonly \
		gs-test-$release
done
