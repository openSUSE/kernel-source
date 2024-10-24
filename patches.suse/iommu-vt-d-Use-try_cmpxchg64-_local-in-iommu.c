From: Uros Bizjak <ubizjak@gmail.com>
Date: Wed, 24 Apr 2024 15:16:28 +0800
Subject: iommu/vt-d: Use try_cmpxchg64{,_local}() in iommu.c
Git-commit: 9e7ee0f045395dc8aa55fbdc164c062484f4c88d
Patch-mainline: v6.10-rc1
References: jsc#PED-10968

Replace this pattern in iommu.c:

    cmpxchg64{,_local}(*ptr, 0, new) != 0

... with the simpler and faster:

    !try_cmpxchg64{,_local}(*ptr, &tmp, new)

The x86 CMPXCHG instruction returns success in the ZF flag, so this change
saves a compare after the CMPXCHG.

No functional change intended.

Signed-off-by: Uros Bizjak <ubizjak@gmail.com>
Cc: David Woodhouse <dwmw2@infradead.org>
Cc: Lu Baolu <baolu.lu@linux.intel.com>
Cc: Joerg Roedel <joro@8bytes.org>
Cc: Will Deacon <will@kernel.org>
Cc: Robin Murphy <robin.murphy@arm.com>
Reviewed-by: Jason Gunthorpe <jgg@nvidia.com>
Link: https://lore.kernel.org/r/20240414162454.49584-1-ubizjak@gmail.com
Signed-off-by: Lu Baolu <baolu.lu@linux.intel.com>
Signed-off-by: Joerg Roedel <jroedel@suse.de>
---
 drivers/iommu/intel/iommu.c |    9 +++++----
 1 file changed, 5 insertions(+), 4 deletions(-)

--- a/drivers/iommu/intel/iommu.c
+++ b/drivers/iommu/intel/iommu.c
@@ -850,7 +850,7 @@ static struct dma_pte *pfn_to_dma_pte(st
 			break;
 
 		if (!dma_pte_present(pte)) {
-			uint64_t pteval;
+			uint64_t pteval, tmp;
 
 			tmp_page = iommu_alloc_page_node(domain->nid, gfp);
 
@@ -862,7 +862,8 @@ static struct dma_pte *pfn_to_dma_pte(st
 			if (domain->use_first_level)
 				pteval |= DMA_FL_PTE_XD | DMA_FL_PTE_US | DMA_FL_PTE_ACCESS;
 
-			if (cmpxchg64(&pte->val, 0ULL, pteval))
+			tmp = 0ULL;
+			if (!try_cmpxchg64(&pte->val, &tmp, pteval))
 				/* Someone else set it while we were thinking; use theirs. */
 				iommu_free_page(tmp_page);
 			else
@@ -2113,8 +2114,8 @@ __domain_mapping(struct dmar_domain *dom
 		/* We don't need lock here, nobody else
 		 * touches the iova range
 		 */
-		tmp = cmpxchg64_local(&pte->val, 0ULL, pteval);
-		if (tmp) {
+		tmp = 0ULL;
+		if (!try_cmpxchg64_local(&pte->val, &tmp, pteval)) {
 			static int dumps = 5;
 			pr_crit("ERROR: DMA PTE for vPFN 0x%lx already set (to %llx not %llx)\n",
 				iov_pfn, tmp, (unsigned long long)pteval);
