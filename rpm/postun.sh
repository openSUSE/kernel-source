if [ -L /boot/vmlinux ]; then
    image=vmlinux
elif [ -L /boot/vmlinuz ]; then
    image=vmlinuz
elif [ -L /boot/image ]; then
    image=image
else
    # nothing to do (UML kernels for example).
    exit 0
fi

# Somewhen in the future: use the real image and initrd filenames instead
# of the symlinks, and add/remove by the real filenames.
#if [ -x /sbin/update-bootloader ]; then
#    /sbin/update-bootloader --image /boot/$image-@KERNELRELEASE@ \
#			     --initrd /boot/initrd-@KERNELRELEASE@ \
#			     --name @KERNELRELEASE@ --remove
#fi

if [ "$(readlink /boot/$image)" = $image-@KERNELRELEASE@ ]; then
    # This may be the last kernel RPM on the system, or it may
    # be an update. In both of those cases the symlinks will
    # eventually be correct. Only if this kernel
    # is removed and other kernel rpms remain installed,
    # find the most recent of the remaining kernels, and make
    # the symlinks point to it. This makes sure that the boot
    # manager will always have a kernel to boot in its default
    # configuration.
    shopt -s nullglob
    for image in $(cd /boot ; ls -dt $image-*); do
	initrd=initrd-${image#*-}
	if [ -f /boot/$image -a -f /boot/$initrd ]; then
	    relink $image /boot/${image%%%%-*}
	    relink $initrd /boot/${initrd%%%%-*}

	    # Notify the boot loader that a new kernel image is active.
	    if [ -x /sbin/update-bootloader ]; then
		/sbin/update-bootloader --image $image \
					--initrd $initrd \
					--refresh
	    fi
	    break
	fi
    done
    shopt -u nullglob
fi

# Created in the other kernel's %post
case "$(readlink /boot/$image.previous)" in
$image-@KERNELRELEASE@|$(readlink /boot/$image))
    if [ -x /sbin/update-bootloader ]; then
	/sbin/update-bootloader --image /boot/$image.previous \
				--initrd /boot/initrd.previous \
				--remove
    fi
    rm -f /boot/$image.previous 
    ;;
esac
case "$(readlink /boot/initrd.previous)" in
initrd-@KERNELRELEASE@|$(readlink /boot/initrd))
    rm -f /boot/initrd.previous ;;
esac
