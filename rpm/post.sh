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
	iseries64)
	    if [ ! -d /proc/iSeries ]; then
		wrong_boardtype "legacy iSeries"
	    fi
	    ;;
	ppc64|kdump)
	    if [ -d /proc/device-tree ]; then
		if [ ! -d /proc/ppc64 -o -d /proc/iSeries ]; then
		    wrong_boardtype "OpenFirmware based 64bit machines"
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

update_bootloader() {
    [ -x /sbin/update-bootloader -a \
      "$YAST_IS_RUNNING" != instsys ] || return 0
    /sbin/update-bootloader "$@"
}

if [ "$YAST_IS_RUNNING" != instsys ]; then
    if [ -f /etc/fstab ]; then
		if ! /sbin/mkinitrd -k /boot/@IMAGE@-@KERNELRELEASE@ \
			-i /boot/initrd-@KERNELRELEASE@; then
			echo "/sbin/mkinitrd failed" >&2
			exit 1
		fi
		
		if [ -x /usr/lib/bootloader/bootloader_entry ]; then
			/usr/lib/bootloader/bootloader_entry \
			add \
			@FLAVOR@ \
			@KERNELRELEASE@ \
			@IMAGE@-@KERNELRELEASE@ \
			initrd-@KERNELRELEASE@

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

					# This is needed only for people who install new kernels on older SUSE Linux products.
					# SUSE Linux does not consider this to be a maintained feature. It is provided as-is.
					echo "bootloader_entry script is not available, using old update-bootloader script."
					update_bootloader --image /boot/@IMAGE@-@KERNELRELEASE@ \
									  --initrd /boot/initrd-@KERNELRELEASE@ \
									  --default \
									  --add \
									  --force $opt_xen_kernel \
									  --name "Kernel-@KERNELRELEASE@"

					update_bootloader --refresh
					;;
			esac
		else
			message_install_bl
		fi
	else
		echo "Please run mkinitrd as soon as your system is complete."
		message_install_bl
	fi
fi
