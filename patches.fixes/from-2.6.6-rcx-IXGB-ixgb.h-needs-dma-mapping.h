#date: 2004-04-15
#id: 1.1371.708.2
#tag: other
#time: 23:55:02
#title: [IXGB]: ixgb.h needs dma-mapping.h
#who: davem@nuts.davemloft.net
#
# ChangeSet
#   1.1371.708.2 04/04/15 23:55:02 davem@nuts.davemloft.net +1 -0
#   [IXGB]: ixgb.h needs dma-mapping.h
#
# drivers/net/ixgb/ixgb.h +1 -0
#
diff -Nru a/drivers/net/ixgb/ixgb.h b/drivers/net/ixgb/ixgb.h
--- a/drivers/net/ixgb/ixgb.h	Wed Apr 28 00:50:06 2004
+++ b/drivers/net/ixgb/ixgb.h	Wed Apr 28 00:50:06 2004
@@ -43,6 +43,7 @@
 #include <linux/timer.h>
 #include <linux/string.h>
 #include <linux/pagemap.h>
+#include <linux/dma-mapping.h>
 #include <linux/bitops.h>
 #include <linux/in.h>
 #include <linux/ip.h>
