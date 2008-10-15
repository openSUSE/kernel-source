# It must be possible to install different kernel.rpm packages in parallel.
# But in this post install script, the /boot/vmlinux symlink is replaced.
# On powerpc, the different kernels are for different board/firmware types
# They are not compatible.
wrong_boardtype() {
    echo "This kernel-@FLAVOR@ is for $1, it will not boot on this system."
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

suffix=
case @FLAVOR@ in
    kdump|ps3|um|xen*)
	suffix=-@FLAVOR@
	;;
esac
for x in /boot/@IMAGE@ /boot/initrd; do
    rm -f $x$suffix
    ln -s ${x##*/}-@KERNELRELEASE@ $x$suffix
done

if [ -e /lib/modules/@KERNELRELEASE@ ]; then
    echo Setting up /lib/modules/@KERNELRELEASE@

    if [ -x /sbin/module_upgrade ]; then
	/sbin/module_upgrade --rename mptscsih="mptspi mptfc mptsas"
    fi
fi
# Add symlinks of compatible modules to /lib/modules/$krel/weak-updates/, 
# run depmod and mkinitrd
wm=/usr/lib/module-init-tools/weak-modules
wm2=/usr/lib/module-init-tools/weak-modules2
if [ -x $wm2 ]; then
    if [ @BASE_PACKAGE@ = 1 ]; then
        $wm2 --add-kernel @KERNELRELEASE@
    else
        nvr=@SUBPACKAGE@-@RPM_VERSION_RELEASE@
        rpm -ql $nvr | $wm2 --add-kernel-modules @KERNELRELEASE@
    fi
elif [ -x $wm ]; then
    # pre CODE11 compatibility
    $wm --add-kernel @KERNELRELEASE@
    /sbin/depmod -a -F /boot/System.map-@KERNELRELEASE@ @KERNELRELEASE@
    if [ -f /etc/fstab -a ! -e /.buildenv -a -x /sbin/mkinitrd ] ; then
        /sbin/mkinitrd -k /boot/@IMAGE@-@KERNELRELEASE@ \
                       -i /boot/initrd-@KERNELRELEASE@
        if [ $? -ne 0 ]; then
            echo "/sbin/mkinitrd failed" >&2
            case @SUBPACKAGE@ in
            *-base)
                echo "Ignoring this for the base subpackage" >&2
                ;;
            *)
                exit 1
                ;;
            esac
        fi
    fi
fi

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

if [ -f /etc/fstab -a ! -e /.buildenv ] ; then
    # only run the bootloader if the usual bootloader configuration
    # files are there -- this is different on every architecture
    initrd=initrd-@KERNELRELEASE@
    if [ -e /boot/$initrd -o ! -e /lib/modules/@KERNELRELEASE@ ] && \
       run_bootloader ; then
       [ -e /boot/$initrd ] || initrd=
	# handle 10.2 and SLES10 SP1 or later
	if [ -x /usr/lib/bootloader/bootloader_entry ]; then
	    /usr/lib/bootloader/bootloader_entry \
		add \
		@FLAVOR@ \
		@KERNELRELEASE@ \
		@IMAGE@-@KERNELRELEASE@ \
		$initrd

	# handle 10.1 and SLES10 GA
	elif [ -x /sbin/update-bootloader ]; then
	    case @FLAVOR@ in
		kdump|um|ps3)
		    ;;
		*)
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
			${initrd:+--initrd /boot/initrd} \
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
