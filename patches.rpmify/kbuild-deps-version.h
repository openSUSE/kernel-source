Fix include/linux/version.h build dependencies

#42972 / LTC9906

When settings in .config that affect include/linux/version.h (like
CONFIG_CFGNAME) are changed, version.h is not updated properly. Add
the required dependency.

Index: linux-2.6.5/Makefile
===================================================================
--- linux-2.6.5.orig/Makefile
+++ linux-2.6.5/Makefile
@@ -703,7 +703,7 @@ define filechk_version.h
 	)
 endef
 
-include/linux/version.h: Makefile
+include/linux/version.h: Makefile .config
 	$(call filechk,version.h)
 
 # ---------------------------------------------------------------------------
