
if test -d /home/ftp/pub/kernel; then
	# kraxel @home
	MIRROR=${MIRROR:-/home/ftp/pub/kernel}
else
	# SuSE DHS
	MIRROR=${MIRROR:-/mounts/mirror/kernel/v2.5}
fi

VERSION=2.5.70
BUILD_DIR=kernel-source-26

