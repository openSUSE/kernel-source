echo Setting up /lib/modules/@KERNELRELEASE@
/sbin/depmod -a -F /boot/System.map-@KERNELRELEASE@ @KERNELRELEASE@

for x in vmlinuz image vmlinux linux; do
    if [ -f /boot/$x-@KERNELRELEASE@ ]; then
	image=$x
	break
    fi
done
if [ -z "$image" ]; then
    exit 1
fi

# The User Mode Linux boot image is called "linux". It cannot be installed
# on the same root filesystem as a native kernel, so we don't run into
# a problem with the /boot/initrd symlink.

# Update the /boot/vmlinuz and /boot/initrd symlinks
case @KERNELRELEASE@ in
    (*xen*|*um*)
    	#nothing to be done
	;;
    (*)	
	for x in /boot/$image /boot/initrd; do
	    if [ -e $x -a "$(readlink $x)" != ${x##*/}-@KERNELRELEASE@ ]; then
		mv -f $x $x.previous
	    fi
	    rm -f $x
	    ln -s ${x##*/}-@KERNELRELEASE@ $x
	done
esac

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

    case @KERNELRELEASE@ in
	(*xen*)
	    # Remove bootsplash picture 
	    mv /boot/initrd-@KERNELRELEASE@ /boot/initrd-@KERNELRELEASE@.gz
	    #echo "gunzipping /boot/initrd-@KERNELRELEASE@.gz"
	    gunzip -f /boot/initrd-@KERNELRELEASE@.gz
	    gzip -9f /boot/initrd-@KERNELRELEASE@
	    ;;
	(*um*)
	    # nothing to be done
    	    ;;
  	(*)	
	    # TODO: Do we need to skip this as well for xen / UML ?
	    if [ -x /sbin/new-kernel-pkg ]; then
	    # Notify boot loader that a new kernel image has been installed.
	    # (during initial installation the boot loader configuration does not
	    #  yet exist when the kernel is installed, but yast kicks the boot
	    #  loader itself later.)
	    /sbin/new-kernel-pkg @KERNELRELEASE@
	    fi
	    ;;
    esac
fi
