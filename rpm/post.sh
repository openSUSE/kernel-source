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

	case @FLAVOR@ in
	    kdump|um)
		;;
	    *)
		opt_xen_kernel=
		case "@FLAVOR@" in
		    xen*)
			set -- @FLAVOR@
			set -- ${1#xen}
			opt_xen_kernel=--xen-kernel=/boot/xen${1:+-$1}.gz
			;;
		esac

		# Make the new kernel the default when installing a non-xen
		# kernel on a non-xen system, or a xen kernel on a xen system.
		opt_default=
		case @FLAVOR@ in
		    xen*)
		        if [[ "$(uname -r)" =~ "xen.*" ]]; then
			    opt_default=--default
			fi
			;;
		    *)
		        if ! [[ "$(uname -r)" =~ "xen.*" ]]; then
			    opt_default=--default
			fi
			;;
		esac

		update_bootloader --image /boot/@IMAGE@-@KERNELRELEASE@ \
				  --initrd /boot/initrd-@KERNELRELEASE@ \
				  --add --force $opt_xen_kernel $opt_default \
				  --name "Kernel-@KERNELRELEASE@"
		update_bootloader --refresh
		;;
	esac
    else
	echo "please run mkinitrd as soon as your system is complete"
    fi
fi
