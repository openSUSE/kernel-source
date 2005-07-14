
if [ -d /home/ftp/pub/kernel ]; then
	# kraxel @home
	MIRROR=${MIRROR:-/home/ftp/pub/kernel}
else
	# SuSE DHS
	MIRROR=${MIRROR:-/mounts/mirror/kernel/v2.6}
fi

# The version of the main tarball to use
SRCVERSION=2.6.12
BUILD_DIR=kernel-source
IGNORE_ARCHS=
