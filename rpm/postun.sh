wm2=/usr/lib/module-init-tools/weak-modules2
if [ @BASE_PACKAGE@ = 0 ]; then
    if [ -x $wm2 ]; then
        nvr=@SUBPACKAGE@-@RPM_VERSION_RELEASE@
        /bin/bash -${-/e/} $wm2 --remove-kernel-modules @KERNELRELEASE@-@FLAVOR@ < /var/run/rpm-$nvr-modules
    fi
    rm -f /var/run/rpm-$nvr-modules
    exit 0
fi
# Remove symlinks from /lib/modules/$krel/weak-updates/.
if [ -x $wm2 ]; then
    /bin/bash -${-/e/} $wm2 --remove-kernel @KERNELRELEASE@-@FLAVOR@
fi

# remove fstab check once perl-Bootloader can cope with it
if [ -f /etc/fstab ]; then
	if [ -x /usr/lib/bootloader/bootloader_entry ]; then
	    /usr/lib/bootloader/bootloader_entry \
		remove \
		@FLAVOR@ \
		@KERNELRELEASE@-@FLAVOR@ \
		@IMAGE@-@KERNELRELEASE@-@FLAVOR@ \
		initrd-@KERNELRELEASE@-@FLAVOR@
	fi
fi
