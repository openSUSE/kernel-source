From aad37dbd563010252e1bedb6dad6cddb867b9235 Mon Sep 17 00:00:00 2001
From: Takashi Iwai <tiwai@suse.de>
Date: Wed, 2 Nov 2011 08:54:51 +0100
Subject: [PATCH] ALSA: hda - Merge input-jack helpers to hda_jack.c
Git-commit: aad37dbd563010252e1bedb6dad6cddb867b9235
Patch-mainline: 3.3-rc1
References: FATE#314311

We can use the very same table in hda_jack.c for managing the list for
input-jack elements, too.

Signed-off-by: Takashi Iwai <tiwai@suse.de>

---
 sound/pci/hda/hda_codec.c      |  108 -----------------------------------------
 sound/pci/hda/hda_jack.c       |   97 ++++++++++++++++++++++++++++++++++++
 sound/pci/hda/hda_jack.h       |    4 +
 sound/pci/hda/hda_local.h      |    4 -
 sound/pci/hda/patch_conexant.c |    1 
 sound/pci/hda/patch_hdmi.c     |    1 
 sound/pci/hda/patch_realtek.c  |    1 
 sound/pci/hda/patch_sigmatel.c |    1 
 8 files changed, 100 insertions(+), 117 deletions(-)

--- a/sound/pci/hda/hda_codec.c
+++ b/sound/pci/hda/hda_codec.c
@@ -5286,113 +5286,5 @@ void snd_print_pcm_bits(int pcm, char *b
 }
 EXPORT_SYMBOL_HDA(snd_print_pcm_bits);
 
-#ifdef CONFIG_SND_HDA_INPUT_JACK
-/*
- * Input-jack notification support
- */
-struct hda_jack_item {
-	hda_nid_t nid;
-	int type;
-	struct snd_jack *jack;
-};
-
-static const char *get_jack_default_name(struct hda_codec *codec, hda_nid_t nid,
-					 int type)
-{
-	switch (type) {
-	case SND_JACK_HEADPHONE:
-		return "Headphone";
-	case SND_JACK_MICROPHONE:
-		return "Mic";
-	case SND_JACK_LINEOUT:
-		return "Line-out";
-	case SND_JACK_LINEIN:
-		return "Line-in";
-	case SND_JACK_HEADSET:
-		return "Headset";
-	case SND_JACK_VIDEOOUT:
-		return "HDMI/DP";
-	default:
-		return "Misc";
-	}
-}
-
-static void hda_free_jack_priv(struct snd_jack *jack)
-{
-	struct hda_jack_item *jacks = jack->private_data;
-	jacks->nid = 0;
-	jacks->jack = NULL;
-}
-
-int snd_hda_input_jack_add(struct hda_codec *codec, hda_nid_t nid, int type,
-			   const char *name)
-{
-	struct hda_jack_item *jack;
-	int err;
-
-	snd_array_init(&codec->jacks, sizeof(*jack), 32);
-	jack = snd_array_new(&codec->jacks);
-	if (!jack)
-		return -ENOMEM;
-
-	jack->nid = nid;
-	jack->type = type;
-	if (!name)
-		name = get_jack_default_name(codec, nid, type);
-	err = snd_jack_new(codec->bus->card, name, type, &jack->jack);
-	if (err < 0) {
-		jack->nid = 0;
-		return err;
-	}
-	jack->jack->private_data = jack;
-	jack->jack->private_free = hda_free_jack_priv;
-	return 0;
-}
-EXPORT_SYMBOL_HDA(snd_hda_input_jack_add);
-
-void snd_hda_input_jack_report(struct hda_codec *codec, hda_nid_t nid)
-{
-	struct hda_jack_item *jacks = codec->jacks.list;
-	int i;
-
-	if (!jacks)
-		return;
-
-	for (i = 0; i < codec->jacks.used; i++, jacks++) {
-		unsigned int pin_ctl;
-		unsigned int present;
-		int type;
-
-		if (jacks->nid != nid)
-			continue;
-		present = snd_hda_jack_detect(codec, nid);
-		type = jacks->type;
-		if (type == (SND_JACK_HEADPHONE | SND_JACK_LINEOUT)) {
-			pin_ctl = snd_hda_codec_read(codec, nid, 0,
-					     AC_VERB_GET_PIN_WIDGET_CONTROL, 0);
-			type = (pin_ctl & AC_PINCTL_HP_EN) ?
-				SND_JACK_HEADPHONE : SND_JACK_LINEOUT;
-		}
-		snd_jack_report(jacks->jack, present ? type : 0);
-	}
-}
-EXPORT_SYMBOL_HDA(snd_hda_input_jack_report);
-
-/* free jack instances manually when clearing/reconfiguring */
-void snd_hda_input_jack_free(struct hda_codec *codec)
-{
-	if (!codec->bus->shutdown && codec->jacks.list) {
-		struct hda_jack_item *jacks = codec->jacks.list;
-		int i;
-		for (i = 0; i < codec->jacks.used; i++, jacks++) {
-			if (jacks->jack)
-				snd_device_free(codec->bus->card, jacks->jack);
-		}
-	}
-	snd_array_free(&codec->jacks);
-}
-EXPORT_SYMBOL_HDA(snd_hda_input_jack_free);
-#endif /* CONFIG_SND_HDA_INPUT_JACK */
-
 MODULE_DESCRIPTION("HDA codec core");
 MODULE_LICENSE("GPL");
--- a/sound/pci/hda/hda_jack.c
+++ b/sound/pci/hda/hda_jack.c
@@ -13,6 +13,7 @@
 #include <linux/slab.h>
 #include <sound/core.h>
 #include <sound/control.h>
+#include <sound/jack.h>
 #include "hda_codec.h"
 #include "hda_local.h"
 #include "hda_jack.h"
@@ -87,8 +88,15 @@ snd_hda_jack_tbl_new(struct hda_codec *c
 	return jack;
 }
 
+#ifdef CONFIG_SND_HDA_INPUT_JACK
+static void snd_hda_input_jack_free(struct hda_codec *codec);
+#else
+#define snd_hda_input_jack_free(codec)
+#endif
+
 void snd_hda_jack_tbl_clear(struct hda_codec *codec)
 {
+	snd_hda_input_jack_free(codec);
 	snd_array_free(&codec->jacktbl);
 }
 
@@ -186,7 +194,7 @@ void snd_hda_jack_report_sync(struct hda
 		if (jack->nid) {
 			jack_detect_update(codec, jack);
 			state = get_jack_plug_state(jack->pin_sense);
-			snd_kctl_jack_notify(codec->bus->card, jack->kctl, state);
+			snd_kctl_jack_report(codec->bus->card, jack->kctl, state);
 		}
 }
 EXPORT_SYMBOL_HDA(snd_hda_jack_report_sync);
@@ -287,3 +295,90 @@ int snd_hda_jack_add_kctls(struct hda_co
 	return 0;
 }
 EXPORT_SYMBOL_HDA(snd_hda_jack_add_kctls);
+
+#ifdef CONFIG_SND_HDA_INPUT_JACK
+/*
+ * Input-jack notification support
+ */
+static const char *get_jack_default_name(struct hda_codec *codec, hda_nid_t nid,
+					 int type)
+{
+	switch (type) {
+	case SND_JACK_HEADPHONE:
+		return "Headphone";
+	case SND_JACK_MICROPHONE:
+		return "Mic";
+	case SND_JACK_LINEOUT:
+		return "Line-out";
+	case SND_JACK_LINEIN:
+		return "Line-in";
+	case SND_JACK_HEADSET:
+		return "Headset";
+	case SND_JACK_VIDEOOUT:
+		return "HDMI/DP";
+	default:
+		return "Misc";
+	}
+}
+
+static void hda_free_jack_priv(struct snd_jack *jack)
+{
+	struct hda_jack_tbl *jacks = jack->private_data;
+	jacks->nid = 0;
+	jacks->jack = NULL;
+}
+
+int snd_hda_input_jack_add(struct hda_codec *codec, hda_nid_t nid, int type,
+			   const char *name)
+{
+	struct hda_jack_tbl *jack = snd_hda_jack_tbl_new(codec, nid);
+	int err;
+
+	if (!jack)
+		return -ENOMEM;
+	if (!name)
+		name = get_jack_default_name(codec, nid, type);
+	err = snd_jack_new(codec->bus->card, name, type, &jack->jack);
+	if (err < 0)
+		return err;
+	jack->jack->private_data = jack;
+	jack->jack->private_free = hda_free_jack_priv;
+	return 0;
+}
+EXPORT_SYMBOL_HDA(snd_hda_input_jack_add);
+
+void snd_hda_input_jack_report(struct hda_codec *codec, hda_nid_t nid)
+{
+	struct hda_jack_tbl *jack = snd_hda_jack_tbl_get(codec, nid);
+	unsigned int pin_ctl;
+	unsigned int present;
+	int type;
+
+	if (!jack)
+		return;
+
+	present = snd_hda_jack_detect(codec, nid);
+	type = jack->type;
+	if (type == (SND_JACK_HEADPHONE | SND_JACK_LINEOUT)) {
+		pin_ctl = snd_hda_codec_read(codec, nid, 0,
+					     AC_VERB_GET_PIN_WIDGET_CONTROL, 0);
+		type = (pin_ctl & AC_PINCTL_HP_EN) ?
+			SND_JACK_HEADPHONE : SND_JACK_LINEOUT;
+	}
+	snd_jack_report(jack->jack, present ? type : 0);
+}
+EXPORT_SYMBOL_HDA(snd_hda_input_jack_report);
+
+/* free jack instances manually when clearing/reconfiguring */
+static void snd_hda_input_jack_free(struct hda_codec *codec)
+{
+	if (!codec->bus->shutdown && codec->jacktbl.list) {
+		struct hda_jack_tbl *jack = codec->jacktbl.list;
+		int i;
+		for (i = 0; i < codec->jacktbl.used; i++, jack++) {
+			if (jack->jack)
+				snd_device_free(codec->bus->card, jack->jack);
+		}
+	}
+}
+#endif /* CONFIG_SND_HDA_INPUT_JACK */
--- a/sound/pci/hda/hda_jack.h
+++ b/sound/pci/hda/hda_jack.h
@@ -22,6 +22,10 @@ struct hda_jack_tbl {
 	unsigned int jack_detect:1;	/* capable of jack-detection? */
 	unsigned int jack_dirty:1;	/* needs to update? */
 	struct snd_kcontrol *kctl;	/* assigned kctl for jack-detection */
+#ifdef CONFIG_SND_HDA_INPUT_JACK
+	int type;
+	struct snd_jack *jack;
+#endif
 };
 
 struct hda_jack_tbl *
--- a/sound/pci/hda/hda_local.h
+++ b/sound/pci/hda/hda_local.h
@@ -685,7 +685,6 @@ void snd_print_channel_allocation(int sp
 int snd_hda_input_jack_add(struct hda_codec *codec, hda_nid_t nid, int type,
 			   const char *name);
 void snd_hda_input_jack_report(struct hda_codec *codec, hda_nid_t nid);
-void snd_hda_input_jack_free(struct hda_codec *codec);
 #else /* CONFIG_SND_HDA_INPUT_JACK */
 static inline int snd_hda_input_jack_add(struct hda_codec *codec,
 					 hda_nid_t nid, int type,
@@ -697,9 +696,6 @@ static inline void snd_hda_input_jack_re
 					     hda_nid_t nid)
 {
 }
-static inline void snd_hda_input_jack_free(struct hda_codec *codec)
-{
-}
 #endif /* CONFIG_SND_HDA_INPUT_JACK */
 
 #endif /* __SOUND_HDA_LOCAL_H */
--- a/sound/pci/hda/patch_conexant.c
+++ b/sound/pci/hda/patch_conexant.c
@@ -474,7 +474,6 @@ static int conexant_init(struct hda_code
 
 static void conexant_free(struct hda_codec *codec)
 {
-	snd_hda_input_jack_free(codec);
 	snd_hda_detach_beep_device(codec);
 	kfree(codec->spec);
 }
--- a/sound/pci/hda/patch_hdmi.c
+++ b/sound/pci/hda/patch_hdmi.c
@@ -1322,7 +1322,6 @@ static void generic_hdmi_free(struct hda
 		cancel_delayed_work(&per_pin->work);
 		snd_hda_eld_proc_free(codec, eld);
 	}
-	snd_hda_input_jack_free(codec);
 
 	flush_workqueue(codec->bus->workq);
 	kfree(spec);
--- a/sound/pci/hda/patch_realtek.c
+++ b/sound/pci/hda/patch_realtek.c
@@ -2489,7 +2489,6 @@ static void alc_free(struct hda_codec *c
 		return;
 
 	alc_shutup(codec);
-	snd_hda_input_jack_free(codec);
 	alc_free_kctls(codec);
 	alc_free_bind_ctls(codec);
 	kfree(spec);
--- a/sound/pci/hda/patch_sigmatel.c
+++ b/sound/pci/hda/patch_sigmatel.c
@@ -4490,7 +4490,6 @@ static void stac92xx_free(struct hda_cod
 		return;
 
 	stac92xx_shutup(codec);
-	snd_hda_input_jack_free(codec);
 
 	kfree(spec);
 	snd_hda_detach_beep_device(codec);
