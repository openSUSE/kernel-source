if [ -f /boot/vmlinuz-%ver_str ]; then
    image=vmlinuz
elif [ -f /boot/image-%ver_str ]; then
    image=image
elif [ -f /boot/vmlinux-%ver_str ]; then
    image=vmlinux
else
    # nothing to do (UML kernels for example).
    exit 0
fi

# If we have old symlinks, rename them to *.previous
if [ -L /boot/$image -a -L /boot/initrd -a \
     "$(readlink /boot/$image)" != $image-%ver_str -a \
     "$(readlink /boot/initrd)" != initrd-%ver_str ]; then
    mv /boot/$image /boot/$image.previous
    mv /boot/initrd /boot/initrd.previous
fi

# update /boot/vmlinuz symlink
relink $image-%ver_str /boot/$image

touch /lib/modules/%ver_str/modules.dep

if test "$YAST_IS_RUNNING" != instsys ; then
    if [ -f /etc/fstab ]; then
	cd /boot
	/sbin/mkinitrd -k $image-%ver_str -i initrd-%ver_str

	if [ -e /boot/initrd-%ver_str ]; then
	    relink initrd-%ver_str /boot/initrd
	else
	    rm -f /boot/initrd
	fi
    else
	echo "please run mkinitrd as soon as your system is complete"
    fi
fi

# $1 is 1 in postinstall if this package is installed
# for the first time and is >1 on update.
if [ "$1" -gt 1 -a -x /sbin/new-kernel-pkg ]; then
    # Notify boot loader that a new kernel image has been installed.
    /sbin/new-kernel-pkg %ver_str
fi
