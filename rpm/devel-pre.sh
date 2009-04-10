# handle update from an older kernel-source with linux-obj as symlink
if [ -h /usr/src/linux-obj ]; then
    rm -vf /usr/src/linux-obj
fi
