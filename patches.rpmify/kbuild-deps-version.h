Fix include/linux/version.h build dependencies

#42972 / LTC9906

When settings in .config that affect include/linux/version.h (like
CONFIG_CFGNAME) are changed, version.h is not updated properly. Add
the required dependency.

Index: linux-2.6.8/Makefile
===================================================================
--- linux-2.6.8.orig/Makefile
+++ linux-2.6.8/Makefile
@@ -804,9 +804,9 @@ define filechk_version.h
 	 echo '#define KERNEL_VERSION(a,b,c) (((a) << 16) + ((b) << 8) + (c))'; \
 	)
 endef
 
-include/linux/version.h: $(srctree)/Makefile FORCE
+include/linux/version.h: $(srctree)/Makefile .config FORCE
 	$(call filechk,version.h)
 
 # ---------------------------------------------------------------------------
 
