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

case @FLAVOR@ in
    kdump|um)
	;;
    *)
	update_bootloader --image /boot/@IMAGE@-@KERNELRELEASE@ \
			  --initrd /boot/initrd-@KERNELRELEASE@ \
			  --name "Kernel-@KERNELRELEASE@" \
			  --remove --force

	if [ "$(readlink /boot/@IMAGE@$suffix)" = \
	     @IMAGE@-@KERNELRELEASE@ ]; then
	    # This symlink has just gone away. Find the most recent of the
	    # remaining kernels, and make the symlinks point to it. This makes
	    # sure that the boot manager will always have a kernel to boot in
	    # its default configuration.
	    shopt -s nullglob
	    for image in $(cd /boot ; ls -dt @IMAGE@-*); do
		initrd=initrd-${image#@IMAGE@-}
		if [ -f /boot/$image -a -f /boot/$initrd ]; then
		    relink $image /boot/@IMAGE@$suffix
		    relink $initrd /boot/initrd$suffix

		    # Trigger the bootloader (e.g., lilo).
		    update_bootloader --refresh
		    break
		fi
	    done
	    shopt -u nullglob
	fi
	;;
esac
