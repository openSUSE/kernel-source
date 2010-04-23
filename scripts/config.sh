MIRROR=${MIRROR:-/mounts/mirror/kernel/v2.6}
if test ! -d "$MIRROR" -a -d /cml/mirror/kernel_v2.6; then
    MIRROR=/cml/mirror/kernel_v2.6
fi
# SRCVERSION and VARIANT are set in rpm/config.sh
if test -e $(dirname -- "$0")/../rpm/config.sh; then
    source "$_"
elif test -e rpm/config.sh; then
    source "$_"
fi
BUILD_DIR=kernel-source${VARIANT}
IGNORE_ARCHS=
DIST_SET=head
