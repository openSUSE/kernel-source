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

update_bootloader() {
    [ -x /sbin/update-bootloader -a \
      "$YAST_IS_RUNNING" != instsys ] || return 0
    /sbin/update-bootloader "$@"
}

if [ -x /usr/lib/bootloader/bootloader_entry ]; then
    /usr/lib/bootloader/bootloader_entry \
	remove \
	@FLAVOR@ \
	@KERNELRELEASE@ \
	@IMAGE@-@KERNELRELEASE@ \
	initrd-@KERNELRELEASE@

elif [ -x /sbin/update-bootloader ]; then
    # This is needed only for people who install new kernels on older SUSE Linux products.
    # SUSE Linux does not consider this to be a maintained feature. It is provided as-is.
    echo "bootloader_entry script is not available, using old update-bootloader script."
    update_bootloader --image /boot/@IMAGE@-@KERNELRELEASE@ \
                      --initrd /boot/initrd-@KERNELRELEASE@ \
                      --remove \
                      --force \
                      --name "Kernel-@KERNELRELEASE@"

    update_bootloader --refresh
fi
