#date: 2004-04-15
#id: 1.1371.708.1
#tag: other
#time: 23:54:31
#title: [E1000]: e1000.h needs dma-mapping.h
#who: davem@nuts.davemloft.net
#
# ChangeSet
#   1.1371.708.1 04/04/15 23:54:31 davem@nuts.davemloft.net +1 -0
#   [E1000]: e1000.h needs dma-mapping.h
#
# drivers/net/e1000/e1000.h +1 -0
#
diff -Nru a/drivers/net/e1000/e1000.h b/drivers/net/e1000/e1000.h
--- a/drivers/net/e1000/e1000.h	Wed Apr 28 00:50:12 2004
+++ b/drivers/net/e1000/e1000.h	Wed Apr 28 00:50:12 2004
@@ -52,6 +52,7 @@
 #include <linux/interrupt.h>
 #include <linux/string.h>
 #include <linux/pagemap.h>
+#include <linux/dma-mapping.h>
 #include <asm/bitops.h>
 #include <asm/io.h>
 #include <asm/irq.h>
