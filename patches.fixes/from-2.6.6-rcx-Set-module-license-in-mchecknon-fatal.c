#date: 2004-04-26
#from: Herbert Xu <herbert@gondor.apana.org.au>
#id: 1.1580
#tag: via-mm
#time: 23:03:56
#title: Set module license in mcheck/non-fatal.c
#who: akpm@osdl.org[torvalds]
#
# ChangeSet
#   1.1580 04/04/26 23:03:56 akpm@osdl.org[torvalds] +1 -0
#   [PATCH] Set module license in mcheck/non-fatal.c
#   
#   From: Herbert Xu <herbert@gondor.apana.org.au>
#   
#   This patch sets the module license for mcheck/non-fatal.c.  The module
#   doesn't work at all without this as one of the symbols it needs is only
#   exported as GPL.
#
# arch/i386/kernel/cpu/mcheck/non-fatal.c +2 -0
#
diff -Nru a/arch/i386/kernel/cpu/mcheck/non-fatal.c b/arch/i386/kernel/cpu/mcheck/non-fatal.c
--- a/arch/i386/kernel/cpu/mcheck/non-fatal.c	Wed Apr 28 10:32:58 2004
+++ b/arch/i386/kernel/cpu/mcheck/non-fatal.c	Wed Apr 28 10:32:58 2004
@@ -88,3 +88,5 @@
 	return 0;
 }
 module_init(init_nonfatal_mce_checker);
+
+MODULE_LICENSE("GPL");
