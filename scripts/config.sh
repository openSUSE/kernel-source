
if [ -d /home/ftp/pub/kernel ]; then
	# kraxel @home
	MIRROR=${MIRROR:-/home/ftp/pub/kernel}
else
	# SuSE DHS
	MIRROR=${MIRROR:-/mounts/mirror/kernel/v2.6}
fi

VERSION=2.6.11
EXTRAVERSION=.3
BUILD_DIR=kernel-source
IGNORE_ARCHS=
