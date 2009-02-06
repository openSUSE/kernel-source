wm=/usr/lib/module-init-tools/weak-modules
wm2=/usr/lib/module-init-tools/weak-modules2
if [ @BASE_PACKAGE@ = 0 ]; then
    if [ -x $wm2 ]; then
        nvr=@SUBPACKAGE@-@RPM_VERSION_RELEASE@
        /bin/bash -${-/e/} $wm2 --remove-kernel-modules @KERNELRELEASE@ < /var/run/rpm-$nvr-modules
    fi
    rm -f /var/run/rpm-$nvr-modules
    exit 0
fi
# Remove symlinks from /lib/modules/$krel/weak-updates/.
if [ -x $wm2 ]; then
    /bin/bash -${-/e/} $wm2 --remove-kernel @KERNELRELEASE@
elif [ -x $wm ]; then
    # pre CODE11 compatibility
    $wm --remove-kernel @KERNELRELEASE@
fi

# remove /boot/@IMAGE@.previous entry on a 10.1 and SLES10 GA system
# when going back from 10.2 or SLES10 SP1 kernel to the original kernel
remove_previos_entry=no
suffix=
case @FLAVOR@ in
    kdump|ps3|xen*|vanilla)
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

# remove fstab check once perl-Bootloader can cope with it
if [ -f /etc/fstab ]; then
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
fi
