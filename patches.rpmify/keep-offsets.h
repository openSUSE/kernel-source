Index: linux-2.6.5/arch/ia64/Makefile
===================================================================
--- linux-2.6.5.orig/arch/ia64/Makefile
+++ linux-2.6.5/arch/ia64/Makefile
@@ -87,7 +87,8 @@ unwcheck: vmlinux
 archclean:
 	$(Q)$(MAKE) $(clean)=$(boot)
 
-CLEAN_FILES += include/asm-ia64/.offsets.h.stamp include/asm-ia64/offsets.h vmlinux.gz bootloader
+CLEAN_FILES += include/asm-ia64/.offsets.h.stamp vmlinux.gz bootloader
+MRPROPER_FILES += include/asm-ia64/offsets.h
 
 prepare: include/asm-ia64/offsets.h
 
Index: linux-2.6.5/arch/m68k/Makefile
===================================================================
--- linux-2.6.5.orig/arch/m68k/Makefile
+++ linux-2.6.5/arch/m68k/Makefile
@@ -112,7 +112,7 @@ else
 endif
 
 prepare: include/asm-$(ARCH)/offsets.h
-CLEAN_FILES += include/asm-$(ARCH)/offsets.h
+MRPROPER_FILES += include/asm-$(ARCH)/offsets.h
 
 arch/$(ARCH)/kernel/asm-offsets.s: include/asm include/linux/version.h \
 				   include/config/MARKER
Index: linux-2.6.5/arch/parisc/Makefile
===================================================================
--- linux-2.6.5.orig/arch/parisc/Makefile
+++ linux-2.6.5/arch/parisc/Makefile
@@ -93,8 +93,8 @@ arch/parisc/kernel/asm-offsets.s: includ
 include/asm-parisc/offsets.h: arch/parisc/kernel/asm-offsets.s
 	$(call filechk,gen-asm-offsets)
 
-CLEAN_FILES	+= lifimage include/asm-parisc/offsets.h
-MRPROPER_FILES	+= palo.conf
+CLEAN_FILES	+= lifimage
+MRPROPER_FILES	+= palo.conf include/asm-parisc/offsets.h
 
 define archhelp
 	@echo  '* vmlinux	- Uncompressed kernel image (./vmlinux)'
Index: linux-2.6.5/arch/ppc/Makefile
===================================================================
--- linux-2.6.5.orig/arch/ppc/Makefile
+++ linux-2.6.5/arch/ppc/Makefile
@@ -107,5 +107,5 @@ checkbin:
 	@true
 endif
 
-CLEAN_FILES +=	include/asm-$(ARCH)/offsets.h \
-		arch/$(ARCH)/kernel/asm-offsets.s
+CLEAN_FILES += arch/$(ARCH)/kernel/asm-offsets.s
+MRPROPER_FILES += include/asm-$(ARCH)/offsets.h
Index: linux-2.6.5/arch/ppc64/Makefile
===================================================================
--- linux-2.6.5.orig/arch/ppc64/Makefile
+++ linux-2.6.5/arch/ppc64/Makefile
@@ -84,4 +84,4 @@ define archhelp
   echo  '		   (arch/$(ARCH)/boot/zImage.initrd)'
 endef
 
-CLEAN_FILES += include/asm-ppc64/offsets.h
+MRPROPER_FILES += include/asm-ppc64/offsets.h
Index: linux-2.6.5/arch/s390/Makefile
===================================================================
--- linux-2.6.5.orig/arch/s390/Makefile
+++ linux-2.6.5/arch/s390/Makefile
@@ -71,7 +71,7 @@ arch/$(ARCH)/kernel/asm-offsets.s: inclu
 include/asm-$(ARCH)/offsets.h: arch/$(ARCH)/kernel/asm-offsets.s
 	$(call filechk,gen-asm-offsets)
 
-CLEAN_FILES += include/asm-$(ARCH)/offsets.h
+MRPROPER_FILES += include/asm-$(ARCH)/offsets.h
 
 # Don't use tabs in echo arguments
 define archhelp
