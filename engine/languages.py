"""Language metadata for Indian scripts and the Whisper backend.

The Indian-language registry is application metadata only.  It does not
bundle copyrighted Bible text.  ``whisper_code`` is deliberately optional:
several Indian languages can be parsed from PDF scripts even though Whisper
does not expose a dedicated language token for forced transcription.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple


@dataclass(frozen=True)
class IndianLanguage:
    """One Indian language supported by the script/PDF workflow."""

    code: str
    name: str
    native_name: str
    scripts: Tuple[str, ...]
    whisper_code: Optional[str] = None

    @property
    def display_name(self) -> str:
        return "%s (%s)" % (self.name, self.native_name)


# India's 22 constitutionally scheduled languages.  Insertion order is used
# by the GUI, with Assamese first because it is the project's primary language.
# Codes are ISO 639 identifiers used for project metadata; a missing
# ``whisper_code`` means the language remains valid for PDF/script processing
# but cannot be forced in Whisper's language selector.
INDIAN_LANGUAGES: Dict[str, IndianLanguage] = {
    "as": IndianLanguage(
        "as", "Assamese", "অসমীয়া", ("Bengali-Assamese",), "as"),
    "bn": IndianLanguage(
        "bn", "Bengali", "বাংলা", ("Bengali-Assamese",), "bn"),
    "brx": IndianLanguage(
        "brx", "Bodo", "बर'", ("Devanagari",)),
    "doi": IndianLanguage(
        "doi", "Dogri", "डोगरी", ("Devanagari", "Takri")),
    "gu": IndianLanguage(
        "gu", "Gujarati", "ગુજરાતી", ("Gujarati",), "gu"),
    "hi": IndianLanguage(
        "hi", "Hindi", "हिन्दी", ("Devanagari",), "hi"),
    "kn": IndianLanguage(
        "kn", "Kannada", "ಕನ್ನಡ", ("Kannada",), "kn"),
    "ks": IndianLanguage(
        "ks", "Kashmiri", "کٲشُر", ("Arabic", "Devanagari")),
    "kok": IndianLanguage(
        "kok", "Konkani", "कोंकणी",
        ("Devanagari", "Roman", "Kannada", "Malayalam")),
    "mai": IndianLanguage(
        "mai", "Maithili", "मैथिली", ("Devanagari", "Tirhuta")),
    "ml": IndianLanguage(
        "ml", "Malayalam", "മലയാളം", ("Malayalam",), "ml"),
    "mni": IndianLanguage(
        "mni", "Manipuri", "ꯃꯤꯇꯩ ꯂꯣꯟ",
        ("Meitei Mayek", "Bengali-Assamese")),
    "mr": IndianLanguage(
        "mr", "Marathi", "मराठी", ("Devanagari",), "mr"),
    "ne": IndianLanguage(
        "ne", "Nepali", "नेपाली", ("Devanagari",), "ne"),
    "or": IndianLanguage(
        "or", "Odia", "ଓଡ଼ିଆ", ("Odia",)),
    "pa": IndianLanguage(
        "pa", "Punjabi", "ਪੰਜਾਬੀ", ("Gurmukhi", "Shahmukhi"), "pa"),
    "sa": IndianLanguage(
        "sa", "Sanskrit", "संस्कृतम्", ("Devanagari",), "sa"),
    "sat": IndianLanguage(
        "sat", "Santali", "ᱥᱟᱱᱛᱟᱲᱤ",
        ("Ol Chiki", "Devanagari", "Bengali-Assamese", "Odia")),
    "sd": IndianLanguage(
        "sd", "Sindhi", "سنڌي", ("Arabic", "Devanagari"), "sd"),
    "ta": IndianLanguage(
        "ta", "Tamil", "தமிழ்", ("Tamil",), "ta"),
    "te": IndianLanguage(
        "te", "Telugu", "తెలుగు", ("Telugu",), "te"),
    "ur": IndianLanguage(
        "ur", "Urdu", "اردو", ("Arabic",), "ur"),
}


def indian_language_options() -> Dict[str, str]:
    """Return all Indian language codes with English and native names."""
    return {
        code: language.display_name
        for code, language in INDIAN_LANGUAGES.items()
    }


def indian_whisper_codes() -> Tuple[str, ...]:
    """Return Indian languages that can safely be forced in Whisper."""
    return tuple(
        language.whisper_code
        for language in INDIAN_LANGUAGES.values()
        if language.whisper_code is not None
    )


def indian_language(code: str) -> Optional[IndianLanguage]:
    """Look up an Indian language by its ISO code."""
    return INDIAN_LANGUAGES.get((code or "").strip().lower())


# Bundled fallback matching Whisper's language-token table. At runtime this is
# merged with the installed Whisper package so future additions appear without
# requiring a GUI code change.
WHISPER_LANGUAGES: Dict[str, str] = {
    "af": "Afrikaans", "am": "Amharic", "ar": "Arabic",
    "as": "Assamese", "az": "Azerbaijani", "ba": "Bashkir",
    "be": "Belarusian", "bg": "Bulgarian", "bn": "Bengali",
    "bo": "Tibetan", "br": "Breton", "bs": "Bosnian",
    "ca": "Catalan", "cs": "Czech", "cy": "Welsh",
    "da": "Danish", "de": "German", "el": "Greek",
    "en": "English", "es": "Spanish", "et": "Estonian",
    "eu": "Basque", "fa": "Persian", "fi": "Finnish",
    "fo": "Faroese", "fr": "French", "gl": "Galician",
    "gu": "Gujarati", "ha": "Hausa", "haw": "Hawaiian",
    "he": "Hebrew", "hi": "Hindi", "hr": "Croatian",
    "ht": "Haitian Creole", "hu": "Hungarian", "hy": "Armenian",
    "id": "Indonesian", "is": "Icelandic", "it": "Italian",
    "ja": "Japanese", "jw": "Javanese", "ka": "Georgian",
    "kk": "Kazakh", "km": "Khmer", "kn": "Kannada",
    "ko": "Korean", "la": "Latin", "lb": "Luxembourgish",
    "ln": "Lingala", "lo": "Lao", "lt": "Lithuanian",
    "lv": "Latvian", "mg": "Malagasy", "mi": "Maori",
    "mk": "Macedonian", "ml": "Malayalam", "mn": "Mongolian",
    "mr": "Marathi", "ms": "Malay", "mt": "Maltese",
    "my": "Myanmar", "ne": "Nepali", "nl": "Dutch",
    "nn": "Nynorsk", "no": "Norwegian", "oc": "Occitan",
    "pa": "Punjabi", "pl": "Polish", "ps": "Pashto",
    "pt": "Portuguese", "ro": "Romanian", "ru": "Russian",
    "sa": "Sanskrit", "sd": "Sindhi", "si": "Sinhala",
    "sk": "Slovak", "sl": "Slovenian", "sn": "Shona",
    "so": "Somali", "sq": "Albanian", "sr": "Serbian",
    "su": "Sundanese", "sv": "Swedish", "sw": "Swahili",
    "ta": "Tamil", "te": "Telugu", "tg": "Tajik",
    "th": "Thai", "tk": "Turkmen", "tl": "Tagalog",
    "tr": "Turkish", "tt": "Tatar", "uk": "Ukrainian",
    "ur": "Urdu", "uz": "Uzbek", "vi": "Vietnamese",
    "yi": "Yiddish", "yo": "Yoruba", "zh": "Chinese",
}


def whisper_language_options() -> Dict[str, str]:
    """Return installed Whisper languages, with a bundled offline fallback."""
    languages = dict(WHISPER_LANGUAGES)
    try:
        from whisper.tokenizer import LANGUAGES
        languages.update({
            str(code): str(name).replace("_", " ").title()
            for code, name in LANGUAGES.items()
        })
    except (ImportError, AttributeError):
        pass
    return languages
