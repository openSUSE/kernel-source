From: garloff@suse.de
Subject: Only remove offsets.h for make mrproper

offsets.h does not need to be removed by make clean.

Index: linux-2.6.10/arch/m68k/Makefile
===================================================================
--- linux-2.6.10.orig/arch/m68k/Makefile
+++ linux-2.6.10/arch/m68k/Makefile
@@ -113,9 +113,9 @@ else
 	bzip2 -1c vmlinux >vmlinux.bz2
 endif
 
 prepare: include/asm-$(ARCH)/offsets.h
-CLEAN_FILES += include/asm-$(ARCH)/offsets.h
+MRPROPER_FILES += include/asm-$(ARCH)/offsets.h
 
 arch/$(ARCH)/kernel/asm-offsets.s: include/asm include/linux/version.h \
 				   include/config/MARKER
 
Index: linux-2.6.10/arch/parisc/Makefile
===================================================================
--- linux-2.6.10.orig/arch/parisc/Makefile
+++ linux-2.6.10/arch/parisc/Makefile
@@ -100,10 +100,10 @@ arch/parisc/kernel/asm-offsets.s: includ
 
 include/asm-parisc/offsets.h: arch/parisc/kernel/asm-offsets.s
 	$(call filechk,gen-asm-offsets)
 
-CLEAN_FILES	+= lifimage include/asm-parisc/offsets.h
-MRPROPER_FILES	+= palo.conf
+CLEAN_FILES	+= lifimage
+MRPROPER_FILES	+= palo.conf include/asm-parisc/offsets.h
 
 define archhelp
 	@echo  '* vmlinux	- Uncompressed kernel image (./vmlinux)'
 	@echo  '  palo		- Bootable image (./lifimage)'
Index: linux-2.6.10/arch/ppc/Makefile
===================================================================
--- linux-2.6.10.orig/arch/ppc/Makefile
+++ linux-2.6.10/arch/ppc/Makefile
@@ -132,8 +132,8 @@ ifneq ($(AS_ALTIVEC),0)
 	@false
 endif
 	@true
 
-CLEAN_FILES +=	include/asm-$(ARCH)/offsets.h \
-		arch/$(ARCH)/kernel/asm-offsets.s \
+CLEAN_FILES += arch/$(ARCH)/kernel/asm-offsets.s \
 		$(TOUT)
+MRPROPER_FILES += include/asm-$(ARCH)/offsets.h
 
Index: linux-2.6.10/arch/ppc64/Makefile
===================================================================
--- linux-2.6.10.orig/arch/ppc64/Makefile
+++ linux-2.6.10/arch/ppc64/Makefile
@@ -91,5 +91,5 @@ define archhelp
   echo  '		   sourced from arch/$(ARCH)/boot/ramdisk.image.gz'
   echo  '		   (arch/$(ARCH)/boot/zImage.initrd)'
 endef
 
-CLEAN_FILES += include/asm-ppc64/offsets.h
+MRPROPER_FILES += include/asm-ppc64/offsets.h
Index: linux-2.6.10/arch/s390/Makefile
===================================================================
--- linux-2.6.10.orig/arch/s390/Makefile
+++ linux-2.6.10/arch/s390/Makefile
@@ -107,9 +107,9 @@ arch/$(ARCH)/kernel/asm-offsets.s: inclu
 
 include/asm-$(ARCH)/offsets.h: arch/$(ARCH)/kernel/asm-offsets.s
 	$(call filechk,gen-asm-offsets)
 
-CLEAN_FILES += include/asm-$(ARCH)/offsets.h
+MRPROPER_FILES += include/asm-$(ARCH)/offsets.h
 
 # Don't use tabs in echo arguments
 define archhelp
   echo  '* image           - Kernel image for IPL ($(boot)/image)'
