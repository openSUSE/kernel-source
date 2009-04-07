MIRROR=${MIRROR:-/mounts/mirror/kernel/v2.6}
if test ! -d "$MIRROR" -a -d /cml/mirror/kernel_v2.6; then
    MIRROR=/cml/mirror/kernel_v2.6
fi
# The version of the main tarball to use
SRCVERSION=2.6.29
# variant of the kernel-source package, either empty or "-rt"
VARIANT=
BUILD_DIR=kernel-source${VARIANT}
IGNORE_ARCHS=
DIST_SET=head
