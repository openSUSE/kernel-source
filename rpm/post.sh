# It must be possible to install different kernel.rpm packages in parallel.
# But in this post install script, the /boot/vmlinux symlink is replaced.
# On powerpc, the different kernels are for different board/firmware types
# They are not compatible.
wrong_boardtype() {
    echo "This kernel is for $1, it will not boot on your system."
    echo "The /boot/vmlinux symlink will not be created or updated."
    exit 0
}
if [ -f /proc/cpuinfo ]; then
    case "@FLAVOR@" in
	ppc64|kdump)
	    if [ -d /proc/device-tree ]; then
		if [ ! -d /proc/ppc64 ]; then
		    wrong_boardtype "OpenFirmware based 64bit machines or legacy iSeries"
		fi
	    fi
	    ;;
	default)
	    if [ -d /proc/ppc64 -o -d /proc/iSeries ]; then
		wrong_boardtype "32bit systems"
	    fi
	    ;;
	*)
	    ;;
    esac
fi

echo Setting up /lib/modules/@KERNELRELEASE@
suffix=
case @FLAVOR@ in
    kdump|um|xen*)
	suffix=-@FLAVOR@
	;;
esac
for x in /boot/@IMAGE@ /boot/initrd; do
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

message_install_bl () {
	echo "You may need to setup and install the boot loader using the"
	echo "available bootloader for your platform (e.g. grub, lilo, zipl, ...)."
}

run_bootloader () {
    if [ -f /etc/sysconfig/bootloader ] &&
	    [ -f /boot/grub/menu.lst -o \
	      -f /etc/lilo.conf      -o \
	      -f /etc/elilo.conf     -o \
	      -f /etc/zipl.conf ]
    then
	return 0
    else
	return 1
    fi
}


if [ -f /etc/fstab ]; then
    if ! /sbin/mkinitrd -k /boot/@IMAGE@-@KERNELRELEASE@ \
	-i /boot/initrd-@KERNELRELEASE@; then
	echo "/sbin/mkinitrd failed" >&2
	exit 1
    fi

    if run_bootloader ; then

	# handle 10.2 and SLES10 SP1
	if [ -x /usr/lib/bootloader/bootloader_entry ]; then
	    /usr/lib/bootloader/bootloader_entry \
		add \
		@FLAVOR@ \
		@KERNELRELEASE@ \
		@IMAGE@-@KERNELRELEASE@ \
		initrd-@KERNELRELEASE@

	# handle 10.1 and SLES10 GA
	elif [ -x /sbin/update-bootloader ]; then
	    case @FLAVOR@ in
		(kdump|um)
		    ;;
		(*)
		    opt_xen_kernel=
		    case @FLAVOR@ in
			xen*)
			    set -- @FLAVOR@
			    set -- ${1#xen}
			    opt_xen_kernel=--xen-kernel=/boot/xen${1:+-$1}.gz
			    ;;
		    esac

		    echo "bootloader_entry script unavailable, updating /boot/@IMAGE@"
		    /sbin/update-bootloader \
			--image /boot/@IMAGE@ \
			--initrd /boot/initrd \
			--add \
			--force $opt_xen_kernel

		    /sbin/update-bootloader --refresh
		    ;;
	    esac
	else
	    message_install_bl
	fi
    fi
else
    echo "Please run mkinitrd as soon as your system is complete."
    message_install_bl
fi

# vim: set sts=4 sw=4 ts=8 noet:
