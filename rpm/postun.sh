# Remove symlinks from /lib/modules/$krel/weak-updates/.
if [ -x /usr/lib/module-init-tools/weak-modules ]; then
    /usr/lib/module-init-tools/weak-modules --remove-kernel @KERNELRELEASE@
fi

suffix=
case @FLAVOR@ in
    kdump|um|xen*)
        suffix=-@FLAVOR@
        ;;
esac

# Created in %post of old kernels
case "$(readlink /boot/@IMAGE@$suffix.previous)" in
@IMAGE@-@KERNELRELEASE@|$(readlink /boot/@IMAGE@$suffix))
    rm -f /boot/@IMAGE@$suffix.previous 
    ;;
esac
case "$(readlink /boot/initrd$suffix.previous)" in
initrd-@KERNELRELEASE@|$(readlink /boot/initrd$suffix))
    rm -f /boot/initrd$suffix.previous
    ;;
esac

if [ -x /usr/lib/bootloader/bootloader_entry ]; then
    /usr/lib/bootloader/bootloader_entry \
	remove \
	kernel-@FLAVOR@-@KERNELRELEASE@.@ARCH@.rpm \
	@IMAGE@-@KERNELRELEASE@ \
	initrd-@KERNELRELEASE@
fi
