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

# update /boot/vmlinuz symlink
if [ -L /boot/$image -a \
     "$(readlink /boot/$image)" != $image-%ver_str ]; then
    mv /boot/$image /boot/$image.previous
fi
relink $image-%ver_str /boot/$image

if test "$YAST_IS_RUNNING" != instsys ; then
    if [ -f /etc/fstab ]; then
	echo Setting up /lib/modules/%ver_str
	/sbin/update-modules.dep -v %ver_str
	cd /boot
	if ! /sbin/mkinitrd -k $image-%ver_str -i initrd-%ver_str; then
	    echo "/sbin/mkinitrd failed" >&2
	    exit 1
	fi

	# update /boot/initrd symlink
	if [ -L /boot/initrd -a \
	     "$(readlink /boot/initrd)" != initrd-%ver_str ]; then
	    mv /boot/initrd /boot/initrd.previous
	fi
	if [ -e /boot/initrd-%ver_str ]; then
	    relink initrd-%ver_str /boot/initrd
	else
	    rm -f /boot/initrd
	fi
    else
	echo "please run mkinitrd as soon as your system is complete"
    fi

    if [ -x /sbin/new-kernel-pkg ]; then
	# Notify boot loader that a new kernel image has been installed.
	# (during initial installation the boot loader configuration does not
	#  yet exist when the kernel is installed, but yast kicks the boot
	#  loader itself later.)
	/sbin/new-kernel-pkg %ver_str
    fi
fi
