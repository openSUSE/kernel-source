From: Alexander Egorenkov <egorenar@linux.ibm.com>
Date: Mon, 5 Jul 2021 19:33:27 +0200
Subject: s390/boot: move uv function declarations to boot/uv.h
Git-commit: c5cf505446db70247a0beb5e70693a5f4754894d
Patch-mainline: v5.15-rc1
References: bsc#1191740 LTC#194817

The functions adjust_to_uv_max() and uv_query_info() are used only
in the decompressor. Therefore, move the function declarations from
the global arch/s390/include/asm/uv.h to arch/s390/boot/uv.h.

Signed-off-by: Alexander Egorenkov <egorenar@linux.ibm.com>
Reviewed-by: Vasily Gorbik <gor@linux.ibm.com>
Signed-off-by: Heiko Carstens <hca@linux.ibm.com>
Acked-by: Petr Tesarik <ptesarik@suse.com>
---
 arch/s390/boot/startup.c   |    1 +
 arch/s390/boot/uv.c        |    2 ++
 arch/s390/boot/uv.h        |   17 +++++++++++++++++
 arch/s390/include/asm/uv.h |    8 --------
 4 files changed, 20 insertions(+), 8 deletions(-)

--- a/arch/s390/boot/startup.c
+++ b/arch/s390/boot/startup.c
@@ -12,6 +12,7 @@
 #include <asm/uv.h>
 #include "compressed/decompressor.h"
 #include "boot.h"
+#include "uv.h"
 
 extern char __boot_data_start[], __boot_data_end[];
 extern char __boot_data_preserved_start[], __boot_data_preserved_end[];
--- a/arch/s390/boot/uv.c
+++ b/arch/s390/boot/uv.c
@@ -3,6 +3,8 @@
 #include <asm/facility.h>
 #include <asm/sections.h>
 
+#include "uv.h"
+
 /* will be used in arch/s390/kernel/uv.c */
 #ifdef CONFIG_PROTECTED_VIRTUALIZATION_GUEST
 int __bootdata_preserved(prot_virt_guest);
--- /dev/null
+++ b/arch/s390/boot/uv.h
@@ -0,0 +1,17 @@
+/* SPDX-License-Identifier: GPL-2.0 */
+#ifndef BOOT_UV_H
+#define BOOT_UV_H
+
+#if IS_ENABLED(CONFIG_KVM)
+void adjust_to_uv_max(unsigned long *vmax);
+#else
+static inline void adjust_to_uv_max(unsigned long *vmax) {}
+#endif
+
+#if defined(CONFIG_PROTECTED_VIRTUALIZATION_GUEST) || IS_ENABLED(CONFIG_KVM)
+void uv_query_info(void);
+#else
+static inline void uv_query_info(void) {}
+#endif
+
+#endif /* BOOT_UV_H */
--- a/arch/s390/include/asm/uv.h
+++ b/arch/s390/include/asm/uv.h
@@ -356,11 +356,9 @@ int uv_convert_from_secure(unsigned long
 int gmap_convert_to_secure(struct gmap *gmap, unsigned long gaddr);
 
 void setup_uv(void);
-void adjust_to_uv_max(unsigned long *vmax);
 #else
 #define is_prot_virt_host() 0
 static inline void setup_uv(void) {}
-static inline void adjust_to_uv_max(unsigned long *vmax) {}
 
 static inline int uv_destroy_page(unsigned long paddr)
 {
@@ -373,10 +371,4 @@ static inline int uv_convert_from_secure
 }
 #endif
 
-#if defined(CONFIG_PROTECTED_VIRTUALIZATION_GUEST) || IS_ENABLED(CONFIG_KVM)
-void uv_query_info(void);
-#else
-static inline void uv_query_info(void) {}
-#endif
-
 #endif /* _ASM_S390_UV_H */
