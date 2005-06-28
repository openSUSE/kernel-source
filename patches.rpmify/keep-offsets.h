From: garloff@suse.de
Subject: Only remove offsets.h for make mrproper

offsets.h does not need to be removed by make clean.

Index: linux-2.6.12/arch/m68k/Makefile
===================================================================
--- linux-2.6.12.orig/arch/m68k/Makefile
+++ linux-2.6.12/arch/m68k/Makefile
@@ -114,7 +114,7 @@ else
 endif
 
 prepare: include/asm-$(ARCH)/offsets.h
-CLEAN_FILES += include/asm-$(ARCH)/offsets.h
+MRPROPER_FILES += include/asm-$(ARCH)/offsets.h
 
 arch/$(ARCH)/kernel/asm-offsets.s: include/asm include/linux/version.h \
 				   include/config/MARKER
Index: linux-2.6.12/arch/parisc/Makefile
===================================================================
--- linux-2.6.12.orig/arch/parisc/Makefile
+++ linux-2.6.12/arch/parisc/Makefile
@@ -108,8 +108,8 @@ arch/parisc/kernel/asm-offsets.s: includ
 include/asm-parisc/offsets.h: arch/parisc/kernel/asm-offsets.s
 	$(call filechk,gen-asm-offsets)
 
-CLEAN_FILES	+= lifimage include/asm-parisc/offsets.h
-MRPROPER_FILES	+= palo.conf
+CLEAN_FILES	+= lifimage
+MRPROPER_FILES	+= palo.conf include/asm-parisc/offsets.h
 
 define archhelp
 	@echo  '* vmlinux	- Uncompressed kernel image (./vmlinux)'
Index: linux-2.6.12/arch/ppc/Makefile
===================================================================
--- linux-2.6.12.orig/arch/ppc/Makefile
+++ linux-2.6.12/arch/ppc/Makefile
@@ -134,7 +134,6 @@ checkbin:
 		false ; \
 	fi
 
-CLEAN_FILES +=	include/asm-$(ARCH)/offsets.h \
-		arch/$(ARCH)/kernel/asm-offsets.s \
+CLEAN_FILES +=	arch/$(ARCH)/kernel/asm-offsets.s \
 		$(TOUT)
-
+MRPROPER_FILES += include/asm-$(ARCH)/offsets.h
Index: linux-2.6.12/arch/ppc64/Makefile
===================================================================
--- linux-2.6.12.orig/arch/ppc64/Makefile
+++ linux-2.6.12/arch/ppc64/Makefile
@@ -128,4 +128,4 @@ define archhelp
   echo  '		   (arch/$(ARCH)/boot/zImage.initrd)'
 endef
 
-CLEAN_FILES += include/asm-ppc64/offsets.h
+MRPROPER_FILES += include/asm-ppc64/offsets.h
Index: linux-2.6.12/arch/s390/Makefile
===================================================================
--- linux-2.6.12.orig/arch/s390/Makefile
+++ linux-2.6.12/arch/s390/Makefile
@@ -108,7 +108,7 @@ arch/$(ARCH)/kernel/asm-offsets.s: inclu
 include/asm-$(ARCH)/offsets.h: arch/$(ARCH)/kernel/asm-offsets.s
 	$(call filechk,gen-asm-offsets)
 
-CLEAN_FILES += include/asm-$(ARCH)/offsets.h
+MRPROPER_FILES += include/asm-$(ARCH)/offsets.h
 
 # Don't use tabs in echo arguments
 define archhelp
