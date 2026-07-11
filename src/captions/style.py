"""Caption style constants — fonts, colors, timing."""
import os

WORDS_PER_CHUNK = 3
FONT_NAME = "Futura Medium"
FONT_SIZE = 82
MARGIN_V = 380

_FONTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "fonts")

CAPTION_FONTS = {
    "futura":       {"ass_name": "Futura Medium",       "file": "/System/Library/Fonts/Supplemental/Futura.ttc",              "fallback": "/System/Library/Fonts/Supplemental/Arial Bold.ttf"},
    "impact":       {"ass_name": "Impact",              "file": "/System/Library/Fonts/Supplemental/Impact.ttf",              "fallback": "/System/Library/Fonts/Supplemental/Arial Black.ttf"},
    "arial-black":  {"ass_name": "Arial Black",         "file": "/System/Library/Fonts/Supplemental/Arial Black.ttf",        "fallback": "/System/Library/Fonts/Supplemental/Arial Bold.ttf"},
    "georgia":      {"ass_name": "Georgia Bold",        "file": "/System/Library/Fonts/Supplemental/Georgia Bold.ttf",       "fallback": "/System/Library/Fonts/Supplemental/Georgia.ttf"},
    "trebuchet":    {"ass_name": "Trebuchet MS Bold",   "file": "/System/Library/Fonts/Supplemental/Trebuchet MS Bold.ttf",  "fallback": "/System/Library/Fonts/Supplemental/Trebuchet MS.ttf"},
    "verdana":      {"ass_name": "Verdana Bold",        "file": "/System/Library/Fonts/Supplemental/Verdana Bold.ttf",       "fallback": "/System/Library/Fonts/Supplemental/Verdana.ttf"},
    "din":          {"ass_name": "DIN Alternate Bold",  "file": "/System/Library/Fonts/Supplemental/DIN Alternate Bold.ttf", "fallback": "/System/Library/Fonts/Supplemental/Arial Bold.ttf"},
    "chalkduster":  {"ass_name": "Chalkduster",         "file": "/System/Library/Fonts/Supplemental/Chalkduster.ttf",        "fallback": "/System/Library/Fonts/Supplemental/Comic Sans MS Bold.ttf"},
    "comic-sans":   {"ass_name": "Comic Sans MS Bold",  "file": "/System/Library/Fonts/Supplemental/Comic Sans MS Bold.ttf", "fallback": "/System/Library/Fonts/Supplemental/Comic Sans MS.ttf"},
    "times":        {"ass_name": "Times New Roman Bold","file": "/System/Library/Fonts/Supplemental/Times New Roman Bold.ttf","fallback": "/System/Library/Fonts/Supplemental/Times New Roman.ttf"},
    "croissant-one":{"ass_name": "Croissant One",       "file": os.path.join(_FONTS_DIR, "CroissantOne-Regular.ttf"),        "fallback": "/System/Library/Fonts/Supplemental/Georgia Bold.ttf"},
}
CAPTION_FONT_CHOICES = list(CAPTION_FONTS.keys())
CAPTION_ANIMATIONS = ["karaoke", "smooth-karaoke", "word", "typing"]

# ASS colors: &HAABBGGRR
PRIMARY_COLOR   = "&H00FFFFFF"   # white
HIGHLIGHT_COLOR = "&H0000CFFF"   # golden yellow
OUTLINE_COLOR   = "&H00000000"   # black
BACK_COLOR      = "&H80000000"   # semi-transparent shadow

# Tension-based highlight gradient (low → high tension)
TENSION_COLORS = [
    "&H00FFCC33",   # calm blue
    "&H0000CFFF",   # golden yellow (default)
    "&H000099FF",   # orange
    "&H000055FF",   # red-orange
    "&H000000FF",   # red (peak)
]
