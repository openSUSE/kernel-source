if [ ! \( -f "/boot/vmlinuz-%ver_str" -o -f "/boot/vmlinux-%ver_str" \) ]; then
	# nothing to do (UML kernels for example).
	exit 0
fi

if [ -f "/boot/vmlinux-%ver_str" ] ; then
boot_file_initrd="vmlinux-%ver_str"
boot_file="/boot/vmlinux-%ver_str"
boot_link="/boot/vmlinux"
else
boot_file_initrd="vmlinuz-%ver_str"
boot_file="/boot/vmlinuz-%ver_str"
boot_link="/boot/vmlinuz"
fi
# update /boot/vmlinuz symlink -- do that only if /boot/vmlinuz
# isn't a real file to avoid removing old kernels where /boot/vmlinuz
# isn't a symlink pointing to the real kernel yet.
if [ -L "$boot_link" -o ! -e "$boot_link" ]; then
	relink "$boot_file" "$boot_link"
	relink initrd-%ver_str /boot/initrd
fi

#if [ -e /etc/sysconfig/kernel ]; then
#    update_rcfile_setting /etc/sysconfig/kernel INITRD_MODULES 2>&1
#elif [ -e /etc/rc.config ]; then
#    update_rcfile_setting /etc/rc.config INITRD_MODULES 2>&1
#fi

touch /lib/modules/%ver_str/modules.dep

if [ -f /etc/fstab ]; then
    cd /boot && \
    /sbin/mkinitrd -k "$boot_file_initrd" -i "initrd-%ver_str"
else
    echo "please run mkinitrd as soon as your system is complete"
fi

# $1 is 1 in postinstall if this package is installed
# for the first time and is >1 on update.
# (AGRUEN: do we really want that?)
if [ "$1" -gt 1 -a -x /sbin/new-kernel-pkg ]; then
    # Notify boot loader that a new kernel image has been installed.
    /sbin/new-kernel-pkg %ver_str
fi

