#!/bin/bash

libdir=$(dirname "$(readlink -f "$0")")

# The sle12-sp2 image is not picked up by registry.suse.de, import it manually
if [ $(docker image ls -q benjamin_poirier/docker_images/sle-12-sp2:latest | wc -l) -ne 1 ]; then
	echo "Fetching base image for sle12-sp2..."
	wget -q -O - http://download.suse.de/ibs/home:/benjamin_poirier:/docker_images:/SLE-12-SP2/images/x86_64/sles12sp2-docker-image.rpm | \
		rpm2cpio - | cpio -i --quiet --to-stdout *.tar.xz | xzcat | \
		docker import - benjamin_poirier/docker_images/sle-12-sp2
fi

for release in \
	sle12-sp2 \
	sle12-sp3 \
	sle15 \
	opensuse-15.0 \
	opensuse-tumbleweed \
	; do
	echo "Building container image for $release..."
	docker build -q -t gs-test-$release "$libdir/$release"
	echo "Running tests in $release:"
	docker run --rm --name=gs-test-$release \
		--mount type=bind,source="$libdir/../../",target=/scripts,readonly \
		gs-test-$release
done
