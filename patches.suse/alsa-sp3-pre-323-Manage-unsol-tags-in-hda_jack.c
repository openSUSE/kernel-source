From 3a93897ea37cbb8277f8a4232c12c0c18168a7db Mon Sep 17 00:00:00 2001
From: Takashi Iwai <tiwai@suse.de>
Date: Fri, 28 Oct 2011 01:16:55 +0200
Subject: [PATCH] ALSA: hda - Manage unsol tags in hda_jack.c
Git-commit: 3a93897ea37cbb8277f8a4232c12c0c18168a7db
Patch-mainline: 3.3-rc1
References: FATE#314106

Manage the tags assigned for unsolicited events dynamically together
with the jack-detection routines.  Basically this is almost same as what
we've done in patch_sigmatel.c.  Assign the new tag number for each new
unsol event, associate with the given NID and the action type, etc.

With this change, now all pins looked over in snd_hda_jack_add_kctls()
are actually enabled for detection now even if the pins aren't used for
jack-retasking by the driver.

Signed-off-by: Takashi Iwai <tiwai@suse.de>

---
 sound/pci/hda/hda_jack.c       |   61 +++++++++++++++---------
 sound/pci/hda/hda_jack.h       |   28 +++++++----
 sound/pci/hda/patch_cirrus.c   |    4 -
 sound/pci/hda/patch_conexant.c |    8 +--
 sound/pci/hda/patch_hdmi.c     |   13 +++--
 sound/pci/hda/patch_realtek.c  |    6 +-
 sound/pci/hda/patch_sigmatel.c |  104 ++++++++++-------------------------------
 sound/pci/hda/patch_via.c      |    3 -
 8 files changed, 104 insertions(+), 123 deletions(-)

--- a/sound/pci/hda/hda_jack.c
+++ b/sound/pci/hda/hda_jack.c
@@ -51,6 +51,24 @@ snd_hda_jack_tbl_get(struct hda_codec *c
 EXPORT_SYMBOL_HDA(snd_hda_jack_tbl_get);
 
 /**
+ * snd_hda_jack_tbl_get_from_tag - query the jack-table entry for the given tag
+ */
+struct hda_jack_tbl *
+snd_hda_jack_tbl_get_from_tag(struct hda_codec *codec, unsigned char tag)
+{
+	struct hda_jack_tbl *jack = codec->jacktbl.list;
+	int i;
+
+	if (!tag || !jack)
+		return NULL;
+	for (i = 0; i < codec->jacktbl.used; i++, jack++)
+		if (jack->tag == tag)
+			return jack;
+	return NULL;
+}
+EXPORT_SYMBOL_HDA(snd_hda_jack_tbl_get_from_tag);
+
+/**
  * snd_hda_jack_tbl_new - create a jack-table entry for the given NID
  */
 struct hda_jack_tbl *
@@ -65,6 +83,7 @@ snd_hda_jack_tbl_new(struct hda_codec *c
 		return NULL;
 	jack->nid = nid;
 	jack->jack_dirty = 1;
+	jack->tag = codec->jacktbl.used;
 	return jack;
 }
 
@@ -77,7 +96,7 @@ void snd_hda_jack_tbl_clear(struct hda_c
 static void jack_detect_update(struct hda_codec *codec,
 			       struct hda_jack_tbl *jack)
 {
-	if (jack->jack_dirty || !jack->jack_cachable) {
+	if (jack->jack_dirty || !jack->jack_detect) {
 		unsigned int val = read_pin_sense(codec, jack->nid);
 		jack->jack_dirty = 0;
 		if (val != jack->pin_sense) {
@@ -141,17 +160,19 @@ EXPORT_SYMBOL_HDA(snd_hda_jack_detect);
  * snd_hda_jack_detect_enable - enable the jack-detection
  */
 int snd_hda_jack_detect_enable(struct hda_codec *codec, hda_nid_t nid,
-			       unsigned int tag)
+			       unsigned char action)
 {
 	struct hda_jack_tbl *jack = snd_hda_jack_tbl_new(codec, nid);
 	if (!jack)
 		return -ENOMEM;
-	if (jack->jack_cachable)
+	if (jack->jack_detect)
 		return 0; /* already registered */
-	jack->jack_cachable = 1;
+	jack->jack_detect = 1;
+	if (action)
+		jack->action = action;
 	return snd_hda_codec_write_cache(codec, nid, 0,
 					 AC_VERB_SET_UNSOLICITED_ENABLE,
-					 AC_USRSP_EN | tag);
+					 AC_USRSP_EN | jack->tag);
 }
 EXPORT_SYMBOL_HDA(snd_hda_jack_detect_enable);
 
@@ -168,18 +189,6 @@ static void jack_detect_report(struct hd
 }
 
 /**
- * snd_hda_jack_report - notify kctl when the jack state was changed
- */
-void snd_hda_jack_report(struct hda_codec *codec, hda_nid_t nid)
-{
-	struct hda_jack_tbl *jack = snd_hda_jack_tbl_get(codec, nid);
-
-	if (jack)
-		jack_detect_report(codec, jack);
-}
-EXPORT_SYMBOL_HDA(snd_hda_jack_report);
-
-/**
  * snd_hda_jack_report_sync - sync the states of all jacks and report if changed
  */
 void snd_hda_jack_report_sync(struct hda_codec *codec)
@@ -231,7 +240,7 @@ int snd_hda_jack_add_kctl(struct hda_cod
 	struct hda_jack_tbl *jack;
 	struct snd_kcontrol *kctl;
 
-	jack = snd_hda_jack_tbl_get(codec, nid);
+	jack = snd_hda_jack_tbl_new(codec, nid);
 	if (!jack)
 		return 0;
 	if (jack->kctl)
@@ -251,20 +260,28 @@ int snd_hda_jack_add_kctl(struct hda_cod
 static int add_jack_kctl(struct hda_codec *codec, hda_nid_t nid, int idx,
 			 const struct auto_pin_cfg *cfg)
 {
+	unsigned int def_conf, conn;
+	int err;
+
 	if (!nid)
 		return 0;
 	if (!is_jack_detectable(codec, nid))
 		return 0;
-	return snd_hda_jack_add_kctl(codec, nid,
+	def_conf = snd_hda_codec_get_pincfg(codec, nid);
+	conn = get_defcfg_connect(def_conf);
+	if (conn != AC_JACK_PORT_COMPLEX)
+		return 0;
+
+	err = snd_hda_jack_add_kctl(codec, nid,
 				     snd_hda_get_pin_label(codec, nid, cfg),
 				     idx);
+	if (err < 0)
+		return err;
+	return snd_hda_jack_detect_enable(codec, nid, 0);
 }
 
 /**
  * snd_hda_jack_add_kctls - Add kctls for all pins included in the given pincfg
- *
- * As of now, it assigns only to the pins that enabled the detection.
- * Usually this is called at the end of build_controls callback.
  */
 int snd_hda_jack_add_kctls(struct hda_codec *codec,
 			   const struct auto_pin_cfg *cfg)
--- a/sound/pci/hda/hda_jack.h
+++ b/sound/pci/hda/hda_jack.h
@@ -14,8 +14,12 @@
 
 struct hda_jack_tbl {
 	hda_nid_t nid;
+	unsigned char action;		/* event action (0 = none) */
+	unsigned char tag;		/* unsol event tag */
+	unsigned int private_data;	/* arbitrary data */
+	/* jack-detection stuff */
 	unsigned int pin_sense;		/* cached pin-sense value */
-	unsigned int jack_cachable:1;	/* can be updated via unsol events */
+	unsigned int jack_detect:1;	/* capable of jack-detection? */
 	unsigned int jack_dirty:1;	/* needs to update? */
 	unsigned int need_notify:1;	/* to be notified? */
 	struct snd_kcontrol *kctl;	/* assigned kctl for jack-detection */
@@ -23,29 +27,34 @@ struct hda_jack_tbl {
 
 struct hda_jack_tbl *
 snd_hda_jack_tbl_get(struct hda_codec *codec, hda_nid_t nid);
+struct hda_jack_tbl *
+snd_hda_jack_tbl_get_from_tag(struct hda_codec *codec, unsigned char tag);
 
 struct hda_jack_tbl *
 snd_hda_jack_tbl_new(struct hda_codec *codec, hda_nid_t nid);
 void snd_hda_jack_tbl_clear(struct hda_codec *codec);
 
 /**
- * snd_hda_jack_set_dirty - set the dirty flag for the given jack-entry
+ * snd_hda_jack_get_action - get jack-tbl entry for the tag
  *
- * Call this function when a pin-state may change, e.g. when the hardware
- * notifies via an unsolicited event.
+ * Call this from the unsol event handler to get the assigned action for the
+ * event.  This will mark the dirty flag for the later reporting, too.
  */
-static inline void snd_hda_jack_set_dirty(struct hda_codec *codec,
-					  hda_nid_t nid)
+static inline unsigned char
+snd_hda_jack_get_action(struct hda_codec *codec, unsigned int tag)
 {
-	struct hda_jack_tbl *jack = snd_hda_jack_tbl_get(codec, nid);
-	if (jack)
+	struct hda_jack_tbl *jack = snd_hda_jack_tbl_get_from_tag(codec, tag);
+	if (jack) {
 		jack->jack_dirty = 1;
+		return jack->action;
+	}
+	return 0;
 }
 
 void snd_hda_jack_set_dirty_all(struct hda_codec *codec);
 
 int snd_hda_jack_detect_enable(struct hda_codec *codec, hda_nid_t nid,
-			       unsigned int tag);
+			       unsigned char action);
 
 u32 snd_hda_pin_sense(struct hda_codec *codec, hda_nid_t nid);
 int snd_hda_jack_detect(struct hda_codec *codec, hda_nid_t nid);
@@ -68,7 +77,6 @@ int snd_hda_jack_add_kctl(struct hda_cod
 int snd_hda_jack_add_kctls(struct hda_codec *codec,
 			   const struct auto_pin_cfg *cfg);
 
-void snd_hda_jack_report(struct hda_codec *codec, hda_nid_t nid);
 void snd_hda_jack_report_sync(struct hda_codec *codec);
 
 
--- a/sound/pci/hda/patch_cirrus.c
+++ b/sound/pci/hda/patch_cirrus.c
@@ -1118,9 +1118,7 @@ static void cs_free(struct hda_codec *co
 
 static void cs_unsol_event(struct hda_codec *codec, unsigned int res)
 {
-	snd_hda_jack_set_dirty_all(codec); /* FIXME: to be more fine-grained */
-
-	switch ((res >> 26) & 0x7f) {
+	switch (snd_hda_jack_get_action(codec, res >> 26)) {
 	case HP_EVENT:
 		cs_automute(codec);
 		break;
--- a/sound/pci/hda/patch_conexant.c
+++ b/sound/pci/hda/patch_conexant.c
@@ -3765,8 +3765,8 @@ static void cx_auto_automic(struct hda_c
 static void cx_auto_unsol_event(struct hda_codec *codec, unsigned int res)
 {
 	int nid = (res & AC_UNSOL_RES_SUBTAG) >> 20;
-	snd_hda_jack_set_dirty(codec, nid);
-	switch (res >> 26) {
+
+	switch (snd_hda_jack_get_action(codec, res >> 26)) {
 	case CONEXANT_HP_EVENT:
 		cx_auto_hp_automute(codec);
 		break;
@@ -3990,11 +3990,11 @@ static void mute_outputs(struct hda_code
 }
 
 static void enable_unsol_pins(struct hda_codec *codec, int num_pins,
-			      hda_nid_t *pins, unsigned int tag)
+			      hda_nid_t *pins, unsigned int action)
 {
 	int i;
 	for (i = 0; i < num_pins; i++)
-		snd_hda_jack_detect_enable(codec, pins[i], tag);
+		snd_hda_jack_detect_enable(codec, pins[i], action);
 }
 
 static void cx_auto_init_output(struct hda_codec *codec)
--- a/sound/pci/hda/patch_hdmi.c
+++ b/sound/pci/hda/patch_hdmi.c
@@ -755,10 +755,18 @@ static void hdmi_present_sense(struct hd
 static void hdmi_intrinsic_event(struct hda_codec *codec, unsigned int res)
 {
 	struct hdmi_spec *spec = codec->spec;
-	int pin_nid = res >> AC_UNSOL_RES_TAG_SHIFT;
+	int tag = res >> AC_UNSOL_RES_TAG_SHIFT;
+	int pin_nid;
 	int pd = !!(res & AC_UNSOL_RES_PD);
 	int eldv = !!(res & AC_UNSOL_RES_ELDV);
 	int pin_idx;
+	struct hda_jack_tbl *jack;
+
+	jack = snd_hda_jack_tbl_get_from_tag(codec, tag);
+	if (!jack)
+		return;
+	pin_nid = jack->nid;
+	jack->jack_dirty = 1;
 
 	printk(KERN_INFO
 		"HDMI hot plug event: Codec=%d Pin=%d Presence_Detect=%d ELD_Valid=%d\n",
@@ -768,7 +776,6 @@ static void hdmi_intrinsic_event(struct
 	if (pin_idx < 0)
 		return;
 
-	snd_hda_jack_set_dirty(codec, pin_nid);
 	hdmi_present_sense(&spec->pins[pin_idx], true);
 	snd_hda_jack_report_sync(codec);
 }
@@ -802,7 +809,7 @@ static void hdmi_unsol_event(struct hda_
 	int tag = res >> AC_UNSOL_RES_TAG_SHIFT;
 	int subtag = (res & AC_UNSOL_RES_SUBTAG) >> AC_UNSOL_RES_SUBTAG_SHIFT;
 
-	if (pin_nid_to_pin_index(spec, tag) < 0) {
+	if (!snd_hda_jack_tbl_get_from_tag(codec, tag)) {
 		snd_printd(KERN_INFO "Unexpected HDMI event tag 0x%x\n", tag);
 		return;
 	}
--- a/sound/pci/hda/patch_realtek.c
+++ b/sound/pci/hda/patch_realtek.c
@@ -184,6 +184,7 @@ struct alc_spec {
 	unsigned int vol_in_capsrc:1; /* use capsrc volume (ADC has no vol) */
 	unsigned int parse_flags; /* passed to snd_hda_parse_pin_defcfg() */
 	unsigned int shared_mic_hp:1; /* HP/Mic-in sharing */
+	unsigned int use_jack_tbl:1; /* 1 for model=auto */
 
 	/* auto-mute control */
 	int automute_mode;
@@ -667,11 +668,13 @@ static void alc_mic_automute(struct hda_
 /* unsolicited event for HP jack sensing */
 static void alc_sku_unsol_event(struct hda_codec *codec, unsigned int res)
 {
+	struct alc_spec *spec = codec->spec;
 	if (codec->vendor_id == 0x10ec0880)
 		res >>= 28;
 	else
 		res >>= 26;
-	snd_hda_jack_set_dirty_all(codec); /* FIXME: to be more fine-grained */
+	if (spec->use_jack_tbl)
+		res = snd_hda_jack_get_action(codec, res);
 	switch (res) {
 	case ALC_HP_EVENT:
 		alc_hp_automute(codec);
@@ -3946,6 +3949,7 @@ static void set_capture_mixer(struct hda
 static void alc_auto_init_std(struct hda_codec *codec)
 {
 	struct alc_spec *spec = codec->spec;
+	spec->use_jack_tbl = 1;
 	alc_auto_init_multi_out(codec);
 	alc_auto_init_extra_out(codec);
 	alc_auto_init_analog_input(codec);
--- a/sound/pci/hda/patch_sigmatel.c
+++ b/sound/pci/hda/patch_sigmatel.c
@@ -175,13 +175,6 @@ enum {
 	STAC_9872_MODELS
 };
 
-struct sigmatel_event {
-	hda_nid_t nid;
-	unsigned char type;
-	unsigned char tag;
-	int data;
-};
-
 struct sigmatel_mic_route {
 	hda_nid_t pin;
 	signed char mux_idx;
@@ -229,9 +222,6 @@ struct sigmatel_spec {
 	const hda_nid_t *pwr_nids;
 	const hda_nid_t *dac_list;
 
-	/* events */
-	struct snd_array events;
-
 	/* playback */
 	struct hda_input_mux *mono_mux;
 	unsigned int cur_mmux;
@@ -4179,49 +4169,18 @@ static int stac92xx_add_jack(struct hda_
 #endif /* CONFIG_SND_HDA_INPUT_JACK */
 }
 
-static int stac_add_event(struct sigmatel_spec *spec, hda_nid_t nid,
+static int stac_add_event(struct hda_codec *codec, hda_nid_t nid,
 			  unsigned char type, int data)
 {
-	struct sigmatel_event *event;
+	struct hda_jack_tbl *event;
 
-	snd_array_init(&spec->events, sizeof(*event), 32);
-	event = snd_array_new(&spec->events);
+	event = snd_hda_jack_tbl_new(codec, nid);
 	if (!event)
 		return -ENOMEM;
-	event->nid = nid;
-	event->type = type;
-	event->tag = spec->events.used;
-	event->data = data;
-
-	return event->tag;
-}
-
-static struct sigmatel_event *stac_get_event(struct hda_codec *codec,
-					     hda_nid_t nid)
-{
-	struct sigmatel_spec *spec = codec->spec;
-	struct sigmatel_event *event = spec->events.list;
-	int i;
-
-	for (i = 0; i < spec->events.used; i++, event++) {
-		if (event->nid == nid)
-			return event;
-	}
-	return NULL;
-}
+	event->action = type;
+	event->private_data = data;
 
-static struct sigmatel_event *stac_get_event_from_tag(struct hda_codec *codec,
-						      unsigned char tag)
-{
-	struct sigmatel_spec *spec = codec->spec;
-	struct sigmatel_event *event = spec->events.list;
-	int i;
-
-	for (i = 0; i < spec->events.used; i++, event++) {
-		if (event->tag == tag)
-			return event;
-	}
-	return NULL;
+	return 0;
 }
 
 /* check if given nid is a valid pin and no other events are assigned
@@ -4231,22 +4190,17 @@ static struct sigmatel_event *stac_get_e
 static int enable_pin_detect(struct hda_codec *codec, hda_nid_t nid,
 			     unsigned int type)
 {
-	struct sigmatel_event *event;
-	int tag;
+	struct hda_jack_tbl *event;
 
 	if (!is_jack_detectable(codec, nid))
 		return 0;
-	event = stac_get_event(codec, nid);
-	if (event) {
-		if (event->type != type)
-			return 0;
-		tag = event->tag;
-	} else {
-		tag = stac_add_event(codec->spec, nid, type, 0);
-		if (tag < 0)
-			return 0;
-	}
-	snd_hda_jack_detect_enable(codec, nid, tag);
+	event = snd_hda_jack_tbl_new(codec, nid);
+	if (!event)
+		return -ENOMEM;
+	if (event->action && event->action != type)
+		return 0;
+	event->action = type;
+	snd_hda_jack_detect_enable(codec, nid, 0);
 	return 1;
 }
 
@@ -4537,7 +4491,6 @@ static void stac92xx_free(struct hda_cod
 
 	stac92xx_shutup(codec);
 	snd_hda_input_jack_free(codec);
-	snd_array_free(&spec->events);
 
 	kfree(spec);
 	snd_hda_detach_beep_device(codec);
@@ -4802,12 +4755,12 @@ static void stac92xx_mic_detect(struct h
 }
 
 static void handle_unsol_event(struct hda_codec *codec,
-			       struct sigmatel_event *event)
+			       struct hda_jack_tbl *event)
 {
 	struct sigmatel_spec *spec = codec->spec;
 	int data;
 
-	switch (event->type) {
+	switch (event->action) {
 	case STAC_HP_EVENT:
 	case STAC_LO_EVENT:
 		stac92xx_hp_detect(codec);
@@ -4817,7 +4770,7 @@ static void handle_unsol_event(struct hd
 		break;
 	}
 
-	switch (event->type) {
+	switch (event->action) {
 	case STAC_HP_EVENT:
 	case STAC_LO_EVENT:
 	case STAC_MIC_EVENT:
@@ -4850,14 +4803,14 @@ static void handle_unsol_event(struct hd
 					  AC_VERB_GET_GPIO_DATA, 0);
 		/* toggle VREF state based on GPIOx status */
 		snd_hda_codec_write(codec, codec->afg, 0, 0x7e0,
-				    !!(data & (1 << event->data)));
+				    !!(data & (1 << event->private_data)));
 		break;
 	}
 }
 
 static void stac_issue_unsol_event(struct hda_codec *codec, hda_nid_t nid)
 {
-	struct sigmatel_event *event = stac_get_event(codec, nid);
+	struct hda_jack_tbl *event = snd_hda_jack_tbl_get(codec, nid);
 	if (!event)
 		return;
 	handle_unsol_event(codec, event);
@@ -4865,15 +4818,14 @@ static void stac_issue_unsol_event(struc
 
 static void stac92xx_unsol_event(struct hda_codec *codec, unsigned int res)
 {
-	struct sigmatel_spec *spec = codec->spec;
-	struct sigmatel_event *event;
+	struct hda_jack_tbl *event;
 	int tag;
 
 	tag = (res >> 26) & 0x7f;
-	event = stac_get_event_from_tag(codec, tag);
+	event = snd_hda_jack_tbl_get_from_tag(codec, tag);
 	if (!event)
 		return;
-	snd_hda_jack_set_dirty(codec, event->nid);
+	event->jack_dirty = 1;
 	handle_unsol_event(codec, event);
 	snd_hda_jack_report_sync(codec);
 }
@@ -5848,15 +5800,13 @@ again:
 		switch (spec->board_config) {
 		case STAC_HP_M4:
 			/* Enable VREF power saving on GPIO1 detect */
-			err = stac_add_event(spec, codec->afg,
+			err = stac_add_event(codec, codec->afg,
 					     STAC_VREF_EVENT, 0x02);
 			if (err < 0)
 				return err;
 			snd_hda_codec_write_cache(codec, codec->afg, 0,
 				AC_VERB_SET_GPIO_UNSOLICITED_RSP_MASK, 0x02);
-			snd_hda_codec_write_cache(codec, codec->afg, 0,
-				AC_VERB_SET_UNSOLICITED_ENABLE,
-				AC_USRSP_EN | err);
+			snd_hda_jack_detect_enable(codec, codec->afg, 0);
 			spec->gpio_mask |= 0x02;
 			break;
 		}
@@ -6327,14 +6277,12 @@ static int patch_stac9205(struct hda_cod
 		snd_hda_codec_set_pincfg(codec, 0x20, 0x1c410030);
 
 		/* Enable unsol response for GPIO4/Dock HP connection */
-		err = stac_add_event(spec, codec->afg, STAC_VREF_EVENT, 0x01);
+		err = stac_add_event(codec, codec->afg, STAC_VREF_EVENT, 0x01);
 		if (err < 0)
 			return err;
 		snd_hda_codec_write_cache(codec, codec->afg, 0,
 			AC_VERB_SET_GPIO_UNSOLICITED_RSP_MASK, 0x10);
-		snd_hda_codec_write_cache(codec, codec->afg, 0,
-					  AC_VERB_SET_UNSOLICITED_ENABLE,
-					  AC_USRSP_EN | err);
+		snd_hda_jack_detect_enable(codec, codec->afg, 0);
 
 		spec->gpio_dir = 0x0b;
 		spec->eapd_mask = 0x01;
--- a/sound/pci/hda/patch_via.c
+++ b/sound/pci/hda/patch_via.c
@@ -1718,9 +1718,8 @@ static void via_gpio_control(struct hda_
 static void via_unsol_event(struct hda_codec *codec,
 				  unsigned int res)
 {
-	snd_hda_jack_set_dirty_all(codec); /* FIXME: to be more fine-grained */
-
 	res >>= 26;
+	res = snd_hda_jack_get_action(codec, res);
 
 	if (res & VIA_JACK_EVENT)
 		set_widgets_power_state(codec);
