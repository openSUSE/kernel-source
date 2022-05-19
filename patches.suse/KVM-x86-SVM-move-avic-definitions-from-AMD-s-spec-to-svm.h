From: Maxim Levitsky <mlevitsk@redhat.com>
Date: Mon, 7 Feb 2022 17:54:26 +0200
Subject: KVM: x86: SVM: move avic definitions from AMD's spec to svm.h
Git-commit: 3915035282573c5e29996ce3173171f5f05234d1
Patch-mainline: v5.17-rc5
References: bsc#1193823 jsc#SLE-24549

asm/svm.h is the correct place for all values that are defined in
the SVM spec, and that includes AVIC.

Also add some values from the spec that were not defined before
and will be soon useful.

Signed-off-by: Maxim Levitsky <mlevitsk@redhat.com>
Message-Id: <20220207155447.840194-10-mlevitsk@redhat.com>
Signed-off-by: Paolo Bonzini <pbonzini@redhat.com>
Acked-by: Joerg Roedel <jroedel@suse.de>
---
 arch/x86/include/asm/msr-index.h |    1 +
 arch/x86/include/asm/svm.h       |   36 ++++++++++++++++++++++++++++++++++++
 arch/x86/kvm/svm/avic.c          |   22 +---------------------
 arch/x86/kvm/svm/svm.h           |   11 -----------
 4 files changed, 38 insertions(+), 32 deletions(-)

--- a/arch/x86/include/asm/msr-index.h
+++ b/arch/x86/include/asm/msr-index.h
@@ -476,6 +476,7 @@
 #define MSR_AMD64_ICIBSEXTDCTL		0xc001103c
 #define MSR_AMD64_IBSOPDATA4		0xc001103d
 #define MSR_AMD64_IBS_REG_COUNT_MAX	8 /* includes MSR_AMD64_IBSBRTARGET */
+#define MSR_AMD64_SVM_AVIC_DOORBELL	0xc001011b
 #define MSR_AMD64_VM_PAGE_FLUSH		0xc001011e
 #define MSR_AMD64_SEV_ES_GHCB		0xc0010130
 #define MSR_AMD64_SEV			0xc0010131
--- a/arch/x86/include/asm/svm.h
+++ b/arch/x86/include/asm/svm.h
@@ -220,6 +220,42 @@ struct __attribute__ ((__packed__)) vmcb
 #define SVM_NESTED_CTL_SEV_ENABLE	BIT(1)
 #define SVM_NESTED_CTL_SEV_ES_ENABLE	BIT(2)
 
+
+/* AVIC */
+#define AVIC_LOGICAL_ID_ENTRY_GUEST_PHYSICAL_ID_MASK	(0xFF)
+#define AVIC_LOGICAL_ID_ENTRY_VALID_BIT			31
+#define AVIC_LOGICAL_ID_ENTRY_VALID_MASK		(1 << 31)
+
+#define AVIC_PHYSICAL_ID_ENTRY_HOST_PHYSICAL_ID_MASK	(0xFFULL)
+#define AVIC_PHYSICAL_ID_ENTRY_BACKING_PAGE_MASK	(0xFFFFFFFFFFULL << 12)
+#define AVIC_PHYSICAL_ID_ENTRY_IS_RUNNING_MASK		(1ULL << 62)
+#define AVIC_PHYSICAL_ID_ENTRY_VALID_MASK		(1ULL << 63)
+#define AVIC_PHYSICAL_ID_TABLE_SIZE_MASK		(0xFF)
+
+#define AVIC_DOORBELL_PHYSICAL_ID_MASK			(0xFF)
+
+#define AVIC_UNACCEL_ACCESS_WRITE_MASK		1
+#define AVIC_UNACCEL_ACCESS_OFFSET_MASK		0xFF0
+#define AVIC_UNACCEL_ACCESS_VECTOR_MASK		0xFFFFFFFF
+
+enum avic_ipi_failure_cause {
+	AVIC_IPI_FAILURE_INVALID_INT_TYPE,
+	AVIC_IPI_FAILURE_TARGET_NOT_RUNNING,
+	AVIC_IPI_FAILURE_INVALID_TARGET,
+	AVIC_IPI_FAILURE_INVALID_BACKING_PAGE,
+};
+
+
+/*
+ * 0xff is broadcast, so the max index allowed for physical APIC ID
+ * table is 0xfe.  APIC IDs above 0xff are reserved.
+ */
+#define AVIC_MAX_PHYSICAL_ID_COUNT	0xff
+
+#define AVIC_HPA_MASK	~((0xFFFULL << 52) | 0xFFF)
+#define VMCB_AVIC_APIC_BAR_MASK		0xFFFFFFFFFF000ULL
+
+
 struct vmcb_seg {
 	u16 selector;
 	u16 attrib;
--- a/arch/x86/kvm/svm/avic.c
+++ b/arch/x86/kvm/svm/avic.c
@@ -27,20 +27,6 @@
 #include "irq.h"
 #include "svm.h"
 
-#define SVM_AVIC_DOORBELL	0xc001011b
-
-#define AVIC_HPA_MASK	~((0xFFFULL << 52) | 0xFFF)
-
-/*
- * 0xff is broadcast, so the max index allowed for physical APIC ID
- * table is 0xfe.  APIC IDs above 0xff are reserved.
- */
-#define AVIC_MAX_PHYSICAL_ID_COUNT	255
-
-#define AVIC_UNACCEL_ACCESS_WRITE_MASK		1
-#define AVIC_UNACCEL_ACCESS_OFFSET_MASK		0xFF0
-#define AVIC_UNACCEL_ACCESS_VECTOR_MASK		0xFFFFFFFF
-
 /* AVIC GATAG is encoded using VM and VCPU IDs */
 #define AVIC_VCPU_ID_BITS		8
 #define AVIC_VCPU_ID_MASK		((1 << AVIC_VCPU_ID_BITS) - 1)
@@ -73,12 +59,6 @@ struct amd_svm_iommu_ir {
 	void *data;		/* Storing pointer to struct amd_ir_data */
 };
 
-enum avic_ipi_failure_cause {
-	AVIC_IPI_FAILURE_INVALID_INT_TYPE,
-	AVIC_IPI_FAILURE_TARGET_NOT_RUNNING,
-	AVIC_IPI_FAILURE_INVALID_TARGET,
-	AVIC_IPI_FAILURE_INVALID_BACKING_PAGE,
-};
 
 /* Note:
  * This function is called from IOMMU driver to notify
@@ -687,7 +667,7 @@ int svm_deliver_avic_intr(struct kvm_vcp
 		int cpuid = vcpu->cpu;
 
 		if (cpuid != get_cpu())
-			wrmsrl(SVM_AVIC_DOORBELL, kvm_cpu_get_apicid(cpuid));
+			wrmsrl(MSR_AMD64_SVM_AVIC_DOORBELL, kvm_cpu_get_apicid(cpuid));
 		put_cpu();
 	} else
 		kvm_vcpu_wake_up(vcpu);
--- a/arch/x86/kvm/svm/svm.h
+++ b/arch/x86/kvm/svm/svm.h
@@ -498,17 +498,6 @@ extern struct kvm_x86_nested_ops svm_nes
 
 /* avic.c */
 
-#define AVIC_LOGICAL_ID_ENTRY_GUEST_PHYSICAL_ID_MASK	(0xFF)
-#define AVIC_LOGICAL_ID_ENTRY_VALID_BIT			31
-#define AVIC_LOGICAL_ID_ENTRY_VALID_MASK		(1 << 31)
-
-#define AVIC_PHYSICAL_ID_ENTRY_HOST_PHYSICAL_ID_MASK	(0xFFULL)
-#define AVIC_PHYSICAL_ID_ENTRY_BACKING_PAGE_MASK	(0xFFFFFFFFFFULL << 12)
-#define AVIC_PHYSICAL_ID_ENTRY_IS_RUNNING_MASK		(1ULL << 62)
-#define AVIC_PHYSICAL_ID_ENTRY_VALID_MASK		(1ULL << 63)
-
-#define VMCB_AVIC_APIC_BAR_MASK		0xFFFFFFFFFF000ULL
-
 static inline void avic_update_vapic_bar(struct vcpu_svm *svm, u64 data)
 {
 	svm->vmcb->control.avic_vapic_bar = data & VMCB_AVIC_APIC_BAR_MASK;
