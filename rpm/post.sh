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
