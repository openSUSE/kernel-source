# If a kernel package is removed before the next reboot, we assume that the
# multiversion variable in /etc/zypp/zypp.conf is not configured and we delete
# the flag again (fate#312018)
rm -f /boot/do_purge_kernels

wm2=/usr/lib/module-init-tools/weak-modules2
nvr=@SUBPACKAGE@-@RPM_VERSION_RELEASE@

if [ -e @SYSTEMMAP@ ]; then
    # the same package was reinstalled or just rebuilt, otherwise the files
    # would have been deleted by now
    # do not remove anything in this case (bnc#533766)
    rm -f /var/run/rpm-$nvr-modules
    exit 0
fi

if [ @BASE_PACKAGE@ = 0 ]; then
    if [ -x $wm2 ]; then
        /bin/bash -${-/e/} $wm2 --remove-kernel-modules @KERNELRELEASE@-@FLAVOR@ < /var/run/rpm-$nvr-modules
    fi
    rm -f /var/run/rpm-$nvr-modules
    exit 0
fi
# Remove symlinks from @MODULESDIR@/weak-updates/.
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
