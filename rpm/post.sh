if [ -f /boot/vmlinuz-%ver_str ]; then
    image_link=vmlinuz
elif [ -f /boot/image-%ver_str ]; then
    image_link=image
elif [ -f /boot/vmlinux-%ver_str ]; then
    image_link=vmlinux
else
    # nothing to do (UML kernels for example).
    exit 0
fi
image=$image_link-%ver_str

# update /boot/vmlinuz symlink -- do that only if /boot/vmlinuz
# isn't a real file to avoid removing old kernels where /boot/vmlinuz
# isn't a symlink pointing to the real kernel yet.
if [ -L /boot/$image_link -o ! -e /boot/$image_link ]; then
	relink $image /boot/$image_link
fi

#if [ -e /etc/sysconfig/kernel ]; then
#    update_rcfile_setting /etc/sysconfig/kernel INITRD_MODULES 2>&1
#elif [ -e /etc/rc.config ]; then
#    update_rcfile_setting /etc/rc.config INITRD_MODULES 2>&1
#fi

touch /lib/modules/%ver_str/modules.dep

if [ -f /etc/fstab ]; then
    cd /boot
    /sbin/mkinitrd -k $image -i initrd-%ver_str

    if [ -L /boot/initrd -o ! -e /boot/initrd ]; then
	if [ -e /boot/initrd-%ver_str ]; then
	    relink initrd-%ver_str /boot/initrd
	elif [ -L /boot/initrd ]; then
	    rm -f /boot/initrd
	fi
    fi
else
    echo "please run mkinitrd as soon as your system is complete"
fi

# $1 is 1 in postinstall if this package is installed
# for the first time and is >1 on update.
if [ "$1" -gt 1 -a -x /sbin/new-kernel-pkg ]; then
    # Notify boot loader that a new kernel image has been installed.
    /sbin/new-kernel-pkg %ver_str
fi
