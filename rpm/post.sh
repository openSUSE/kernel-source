echo Setting up /lib/modules/@KERNELRELEASE@
for x in vmlinuz image vmlinux linux bzImage; do
    if [ -f /boot/$x-@KERNELRELEASE@ ]; then
	image=$x
	break
    fi
done
if [ -z "$image" ]; then
    exit 1
fi

# Update the /boot/vmlinuz and /boot/initrd symlinks, and rename
# existing symlinks to *.previous.
suffix=
case @FLAVOR@ in
    (kdump|um|xen*)
	suffix=-@FLAVOR@
	;;
esac
for x in /boot/$image /boot/initrd; do
    if [ -e $x$suffix -a \
	 "$(readlink $x$suffix)" != ${x##*/}-@KERNELRELEASE@ ]; then
	mv -f $x$suffix $x$suffix.previous
    fi
    rm -f $x$suffix
    ln -s ${x##*/}-@KERNELRELEASE@ $x$suffix
done

if [ -x /sbin/module_upgrade ]; then
    /sbin/module_upgrade --rename mptscsih="mptspi mptfc mptsas"
fi

# Add symlinks of compatible modules to /lib/modules/$krel/weak-updates/.
if [ -x /usr/lib/module-init-tools/weak-modules ]; then
    /usr/lib/module-init-tools/weak-modules --add-kernel @KERNELRELEASE@
fi
/sbin/depmod -a -F /boot/System.map-@KERNELRELEASE@ @KERNELRELEASE@

update_bootloader() {
    [ -x /sbin/update-bootloader -a \
      "$YAST_IS_RUNNING" != instsys ] || return 0
    /sbin/update-bootloader "$@"
}

if [ "$YAST_IS_RUNNING" != instsys ]; then
    if [ -f /etc/fstab ]; then
	if ! /sbin/mkinitrd -k /boot/$image-@KERNELRELEASE@ \
			    -i /boot/initrd-@KERNELRELEASE@; then
	    echo "/sbin/mkinitrd failed" >&2
	    exit 1
	fi
    else
	echo "please run mkinitrd as soon as your system is complete"
    fi

    case @FLAVOR@ in
	(kdump|um|xen*)
    	    ;;
  	(*)	
	    if [ -e /boot/$image.previous -a -e /boot/initrd.previous ]; then
		# Only create Previous Kernel bootloader entries for
		# kernels >= 2.6.16; older kernels don't know how to
		# remove their bootloader entries again in their %postun.
		set -- $(readlink /boot/$image.previous \
			 | sed -nr -e 's:\.: :g' \
				   -e 's:.*([0-9]+ [0-9]+ [0-9]+).*:\1:p')
		if [ -n "$1" ] && (( ($1*100 + $2) * 100 + $3 >= 20616)); then
		    update_bootloader --image /boot/$image.previous \
				      --initrd /boot/initrd.previous \
				      --previous --add --force \
				      $(case "$1" in (*-xen*) echo --xen;; esac)
		fi
	    fi
	    ;;
    esac
    update_bootloader --image /boot/$image \
		      --initrd /boot/initrd \
		      --add --force \
		      $(case "@FLAVOR@" in (xen*) echo --xen;; esac)

    # Somewhen in the future: use the real image and initrd filenames instead
    # of the symlinks, and add/remove by the real filenames.
    #    update_bootloader --image /boot/$image-@KERNELRELEASE@ \
    #			   --initrd /boot/initrd-@KERNELRELEASE@ \
    #			   --name @KERNELRELEASE@ --add --force

    # Run the bootloader (e.g., lilo).
    update_bootloader --refresh
fi
