"""ScriptureSound QC desktop GUI package."""
import os
import sys

from engine.config import default_config_path


def apply_font_workaround():
    """Hide WOFF fonts from Qt on Linux before the QApplication is created.

    Qt's FreeType backend cannot load WOFF files, and some distro packages
    (for example fonts-opendyslexic) register them with fontconfig. Shaping
    Indic text through one of them segfaults inside Qt 6.11.
    """
    if sys.platform != "linux" or os.environ.get("FONTCONFIG_FILE"):
        return
    conf = os.path.join(os.path.dirname(default_config_path()), "fonts.conf")
    with open(conf, "w", encoding="utf-8") as stream:
        stream.write(
            '<?xml version="1.0"?><!DOCTYPE fontconfig SYSTEM "fonts.dtd">\n'
            '<fontconfig><include ignore_missing="yes">/etc/fonts/fonts.conf</include>\n'
            '<selectfont><rejectfont><glob>/*.woff</glob><glob>/*.woff2</glob>'
            '</rejectfont></selectfont></fontconfig>\n')
    os.environ["FONTCONFIG_FILE"] = conf


apply_font_workaround()
