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

# Update the /boot/vmlinuz and /boot/initrd symlinks
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

if [ "$YAST_IS_RUNNING" != instsys -a -n "$run_mkinitrd" ]; then
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
                echo "updating bootloader configuration"
		/sbin/update-bootloader --image /boot/$image.previous \
					--initrd /boot/initrd.previous \
					--previous --add
	    fi
	    ;;
    esac
fi

# Somewhen in the future: use the real image and initrd filenames instead
# of the symlinks, and add/remove by the real filenames.
#if [ -x /sbin/update-bootloader ]; then
#    /sbin/update-bootloader --image /boot/$image-@KERNELRELEASE@ \
#			     --initrd /boot/initrd-@KERNELRELEASE@ \
#			     --name @KERNELRELEASE@ --add
#fi
