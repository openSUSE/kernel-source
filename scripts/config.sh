
if test -d /home/ftp/pub/kernel; then
	# kraxel @home
	MIRROR=${MIRROR:-/home/ftp/pub/kernel}
else
	# SuSE DHS
	MIRROR=${MIRROR:-/mounts/mirror/kernel/v2.6}
fi

VERSION=2.6.0-test3
BUILD_DIR=kernel-source-26

