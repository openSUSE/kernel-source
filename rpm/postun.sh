rm -f /boot/initrd-%ver_str  # created in %post -- clean up.

if [ "$(readlink /boot/vmlinuz)" = vmlinuz-%ver_str -o \
     "$(readlink /boot/vmlinux)" = vmlinux-%ver_str -o \
     "$(readlink /boot/initrd)"  = initrd-%ver_str -o \
     "$(readlink /boot/image)"   = image-%ver_str ]; then
    # This may be the last kernel RPM on the system, or it may
    # be an update. In both of those cases the symlinks will
    # eventually be correct. Only if this kernel
    # is removed and other kernel rpms remain installed,
    # find the most recent of the remaining kernels, and make
    # the symlinks point to it. This makes sure that the boot
    # manager will always have a kernel to boot in its default
    # configuration.
    shopt -s nullglob
    for image in $(cd /boot ; ls -dt vmlinu[xz]-* image-*); do
	initrd=initrd-${image#*-}
	if [ -f /boot/$image -a -f /boot/$initrd ]; then
	    relink $image /boot/image
	    relink $initrd /boot/initrd
	    break
	fi
    done
    shopt -u nullglob
fi
