# Remove symlinks from /lib/modules/$krel/weak-updates/.
if [ -x /usr/lib/module-init-tools/weak-modules ]; then
    /usr/lib/module-init-tools/weak-modules --remove-kernel @KERNELRELEASE@
fi

# remove /boot/@IMAGE@.previous entry on a 10.1 and SLES10 GA system
# when going back from 10.2 or SLES10 SP1 kernel to the original kernel
remove_previos_entry=no
suffix=
case @FLAVOR@ in
    kdump|um|xen*)
        suffix=-@FLAVOR@
        ;;
esac

# Created in %post of old kernels
case "$(readlink /boot/@IMAGE@$suffix.previous)" in
@IMAGE@-@KERNELRELEASE@|$(readlink /boot/@IMAGE@$suffix))
    remove_previos_entry=yes
    rm -f /boot/@IMAGE@$suffix.previous 
    ;;
esac
case "$(readlink /boot/initrd$suffix.previous)" in
initrd-@KERNELRELEASE@|$(readlink /boot/initrd$suffix))
    rm -f /boot/initrd$suffix.previous
    ;;
esac

# handle 10.2 and SLES10 SP1
if [ -x /usr/lib/bootloader/bootloader_entry ]; then
    /usr/lib/bootloader/bootloader_entry \
	remove \
	@FLAVOR@ \
	@KERNELRELEASE@ \
	@IMAGE@-@KERNELRELEASE@ \
	initrd-@KERNELRELEASE@

# handle 10.1 and SLES10 GA
elif [ -x /sbin/update-bootloader ]; then
	if [ "$remove_previos_entry" = "yes" ] ; then
		/sbin/update-bootloader	--image /boot/@IMAGE@$suffix.previous \
					--initrd /boot/initrd$suffix.previous \
					--remove --force
	fi
	/sbin/update-bootloader --refresh
fi
