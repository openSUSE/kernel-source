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
NOBOOTSPLASH=
suffix=
case @KERNELRELEASE@ in
    (*xen*)
	NOBOOTSPLASH="-s off"
	suffix=-xen
	;;
    (*um*)
	NOBOOTSPLASH="-s off"
	suffix=-um
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
			    -i /boot/initrd-@KERNELRELEASE@ $NOBOOTSPLASH; then
	    echo "/sbin/mkinitrd failed" >&2
	    exit 1
	fi
    else
	echo "please run mkinitrd as soon as your system is complete"
    fi

    case @KERNELRELEASE@ in
	(*xen*|*um*)
    	    ;;
  	(*)	
	    #if [ -x /sbin/update-bootloader ]; then
	    #	opt_initrd=
	    #	[ -e /boot/initrd-@KERNELRELEASE@ ] \
	    #	    && opt_initrd="--initrd /boot/initrd-@KERNELRELEASE@"
	    #	/sbin/update-bootloader --image /boot/$image-@KERNELRELEASE@ \
	    #	    $opt_initrd --add --default
	    #fi
	    if [ -x /sbin/new-kernel-pkg ]; then
		# Notify boot loader that a new kernel image has been installed.
		# (during initial installation the boot loader configuration
		# does not yet exist when the kernel is installed, but yast
		# kicks the boot loader itself later.)
		/sbin/new-kernel-pkg @KERNELRELEASE@
	    fi
	    ;;
    esac
fi
