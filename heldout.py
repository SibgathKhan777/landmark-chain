"""Held-out extraction check. These phrases were written AFTER the first unseen-phrase check and are NOT used to tune
the lexicon. Labels are hand-written: {slot: {canonical values}}. Anchors/colours the lexicon lacks are labelled anyway."""
HELDOUT = [
 ("मंडई के पीछे नीला दरवाजा", {"anchor": {"MARKET"}, "relation": {"BEHIND"}, "colour": {"BLUE"}}),
 ("अस्पताल के सामने पहली गली", {"anchor": {"HOSPITAL"}, "relation": {"FRONT"}, "ordinal": {"1"}}),
 ("चौक के पास हरा मकान", {"anchor": {"CHOWK"}, "relation": {"NEAR"}, "colour": {"GREEN"}}),
 ("दायें तरफ दूसरी दुकान", {"side": {"RIGHT"}, "ordinal": {"2"}}),
 ("सफेद घर के पीछे गली", {"colour": {"WHITE"}, "relation": {"BEHIND"}}),
 ("काळ्या गेटच्या समोर", {"colour": {"BLACK"}, "relation": {"FRONT"}}),
 ("बँकेजवळ गुलाबी घर", {"anchor": {"BANK"}, "relation": {"NEAR"}, "colour": {"PINK"}}),
 ("शाळेनंतर तिसरे घर", {"anchor": {"SCHOOL"}, "relation": {"AFTER"}, "ordinal": {"3"}}),
 ("पुलावर पिवळे दुकान", {"anchor": {"BRIDGE"}, "relation": {"ABOVE"}, "colour": {"YELLOW"}}),
 ("tank ke upar neela ghar", {"anchor": {"TANK"}, "relation": {"ABOVE"}, "colour": {"BLUE"}}),
 ("school ke peeche doosri gali", {"anchor": {"SCHOOL"}, "relation": {"BEHIND"}, "ordinal": {"2"}}),
 ("masjid ke paas hara gate", {"anchor": {"MOSQUE"}, "relation": {"NEAR"}, "colour": {"GREEN"}}),
 ("लालू की दुकान के पीछे", {"relation": {"BEHIND"}}),
 ("नीलम की गली के सामने", {"relation": {"FRONT"}}),
 ("चहा टपरी के बाद डावीकडे वळा", {"anchor": {"TEA_STALL"}, "relation": {"AFTER"}, "side": {"LEFT"}}),
]


# Set A: the first unseen-phrase check (25 phrases). Run before any lexicon fix; the lexicon was extended afterwards
# using what it missed, so set A is in-sample now.
HELDOUT_A = [
 ("चाय की टपरी के पास नीली दुकान", {"anchor": {"TEA_STALL"}, "relation": {"NEAR"}, "colour": {"BLUE"}}),
 ("बिजली के खंबे के सामने लाल गेट", {"anchor": {"POLE"}, "relation": {"FRONT"}, "colour": {"RED"}}),
 ("स्कूल के बाईं तरफ वाली गली", {"anchor": {"SCHOOL"}, "side": {"LEFT"}}),
 ("तीसरी मंजिल पर नीला दरवाजा", {"ordinal": {"3"}, "colour": {"BLUE"}}),
 ("गणपति मंदिर के बाद दूसरा मकान", {"anchor": {"TEMPLE"}, "relation": {"AFTER"}, "ordinal": {"2"}}),
 ("पुल के नीचे हरा गेट", {"anchor": {"BRIDGE"}, "relation": {"BELOW"}, "colour": {"GREEN"}}),
 ("बैंक के ऊपर वाला फ्लैट", {"anchor": {"BANK"}, "relation": {"ABOVE"}}),
 ("कोने की पीली बिल्डिंग", {"colour": {"YELLOW"}}),
 ("सफेद रंग का मकान", {"colour": {"WHITE"}}),
 ("दायें हाथ पर पहली गली", {"side": {"RIGHT"}, "ordinal": {"1"}}),
 ("चहाच्या टपरीजवळ निळे दुकान", {"anchor": {"TEA_STALL"}, "relation": {"NEAR"}, "colour": {"BLUE"}}),
 ("हनुमान मंदिराच्या समोर पिवळे घर", {"anchor": {"HANUMAN", "TEMPLE"}, "relation": {"FRONT"}, "colour": {"YELLOW"}}),
 ("दुसऱ्या मजल्यावर लाल दरवाजा", {"ordinal": {"2"}, "colour": {"RED"}}),
 ("पुलाखाली हिरवे गेट", {"anchor": {"BRIDGE"}, "relation": {"BELOW"}, "colour": {"GREEN"}}),
 ("बँकेच्या वर पांढरे घर", {"anchor": {"BANK"}, "relation": {"ABOVE"}, "colour": {"WHITE"}}),
 ("शाळेच्या डाव्या बाजूला गल्ली", {"anchor": {"SCHOOL"}, "side": {"LEFT"}}),
 ("तिसऱ्या गल्लीत काळे गेट", {"ordinal": {"3"}, "colour": {"BLACK"}}),
 ("वडाच्या झाडामागे निळे घर", {"anchor": {"TREE"}, "relation": {"BEHIND"}, "colour": {"BLUE"}}),
 ("मारुती मंदिरासमोर हिरवे गेट", {"anchor": {"HANUMAN", "TEMPLE"}, "relation": {"FRONT"}, "colour": {"GREEN"}}),
 ("पाण्याच्या टाकीमागे पहिले दुकान", {"anchor": {"TANK"}, "relation": {"BEHIND"}, "ordinal": {"1"}}),
 ("temple ke peeche neela gate", {"anchor": {"TEMPLE"}, "relation": {"BEHIND"}, "colour": {"BLUE"}}),
 ("school ke saamne laal ghar", {"anchor": {"SCHOOL"}, "relation": {"FRONT"}, "colour": {"RED"}}),
 ("लाल बाग के पास पीला मकान", {"relation": {"NEAR"}, "colour": {"YELLOW"}}),
 ("सावित्रीबाई फुले चौक के पीछे", {"anchor": {"CHOWK"}, "relation": {"BEHIND"}}),
 ("हरीश की दुकान के पीछे", {"relation": {"BEHIND"}}),
]

# Set C: written after the fixes and never used to tune anything. This is the honest generalisation estimate.
HELDOUT_C = [
 ("पान की दुकान के बगल में नीला गेट", {"anchor": {"PAN_SHOP"}, "relation": {"NEAR"}, "colour": {"BLUE"}}),
 ("मेडिकल स्टोर के सामने तीसरी गली", {"anchor": {"MEDICAL"}, "relation": {"FRONT"}, "ordinal": {"3"}}),
 ("नीम के पेड़ के नीचे पीला घर", {"anchor": {"TREE"}, "relation": {"BELOW"}, "colour": {"YELLOW"}}),
 ("बाएं हाथ पर दूसरा मकान", {"side": {"LEFT"}, "ordinal": {"2"}}),
 ("गुरुद्वारे के पीछे हरा दरवाजा", {"anchor": {"GURUDWARA"}, "relation": {"BEHIND"}, "colour": {"GREEN"}}),
 ("चर्च के पास लाल गेट", {"anchor": {"CHURCH"}, "relation": {"NEAR"}, "colour": {"RED"}}),
 ("रेलवे स्टेशन के सामने पहली दुकान", {"anchor": {"STATION"}, "relation": {"FRONT"}, "ordinal": {"1"}}),
 ("नदीच्या पुलाजवळ निळे घर", {"anchor": {"BRIDGE"}, "relation": {"NEAR"}, "colour": {"BLUE"}}),
 ("दुसऱ्या चौकानंतर उजवीकडे", {"anchor": {"CHOWK"}, "relation": {"AFTER"}, "ordinal": {"2"}, "side": {"RIGHT"}}),
 ("हॉटेलच्या मागे हिरवा दरवाजा", {"anchor": {"HOTEL"}, "relation": {"BEHIND"}, "colour": {"GREEN"}}),
 ("kirana ke saamne peeli building", {"anchor": {"KIRANA"}, "relation": {"FRONT"}, "colour": {"YELLOW"}}),
 ("mandir ke baad teesri gali", {"anchor": {"TEMPLE"}, "relation": {"AFTER"}, "ordinal": {"3"}}),
 ("right side pe pehla ghar", {"side": {"RIGHT"}, "ordinal": {"1"}}),
 ("बजरंग बली मंदिर के पीछे सफेद घर", {"anchor": {"TEMPLE"}, "relation": {"BEHIND"}, "colour": {"WHITE"}}),
 ("हरी भाई की चाय की दुकान के पास", {"relation": {"NEAR"}, "anchor": {"TEA_STALL"}}),
]

SETS = [
    ("A", "first unseen set; extended afterwards using its misses, so in-sample now", HELDOUT_A),
    ("B", "second set; extended afterwards using its misses, so in-sample now", HELDOUT),
    ("C", "written after the fixes, never used for tuning", HELDOUT_C),
]
