if [ @BASE_PACKAGE@ = 0 ]; then
    nvr=@SUBPACKAGE@-@RPM_VERSION_RELEASE@
    rpm -ql $nvr | grep '\.ko$' > /var/run/rpm-$nvr-modules
fi
