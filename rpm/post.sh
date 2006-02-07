echo Setting up /lib/modules/@KERNELRELEASE@
/sbin/depmod -a -F /boot/System.map-@KERNELRELEASE@ @KERNELRELEASE@

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
for x in /boot/$image$suffix /boot/initrd$suffix; do
    if [ -e $x -a \
	 "$(readlink $x)" != ${x##*/}-@KERNELRELEASE@ ]; then
	mv -f $x $x.previous
    fi
    rm -f $x
    ln -s ${x##*/}-@KERNELRELEASE@ $x
done

if [ -x /sbin/module_upgrade ]; then
    /sbin/module_upgrade --rename mptscsih="mptspi mptfc mptsas"
fi

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
	    if [ -x /sbin/update-bootloader -a \
		 -e /boot/$image.previous -a \
		 -e /boot/initrd.previous ]; then
		/sbin/update-bootloader --image /boot/$image.previous \
					--initrd /boot/initrd.previous \
					--previous --add --force
	    fi
	    ;;
    esac
    /sbin/update-bootloader --image /boot/$image \
			    --initrd /boot/initrd \
			    --add --force

    # Somewhen in the future: use the real image and initrd filenames instead
    # of the symlinks, and add/remove by the real filenames.
    #if [ -x /sbin/update-bootloader ]; then
    #    /sbin/update-bootloader --image /boot/$image-@KERNELRELEASE@ \
    #			     --initrd /boot/initrd-@KERNELRELEASE@ \
    #			     --name @KERNELRELEASE@ --add --force
    #fi

    # Run the bootloader (e.g., lilo).
    /sbin/update-bootloader --refresh
fi
