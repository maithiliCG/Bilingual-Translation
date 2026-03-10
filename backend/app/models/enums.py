"""Supported Indian regional languages."""

SUPPORTED_LANGUAGES = [
    {"code": "te", "name": "Telugu", "native_name": "తెలుగు"},
    {"code": "hi", "name": "Hindi", "native_name": "हिन्दी"},
    {"code": "ta", "name": "Tamil", "native_name": "தமிழ்"},
    {"code": "kn", "name": "Kannada", "native_name": "ಕನ್ನಡ"},
    {"code": "ml", "name": "Malayalam", "native_name": "മലയാളം"},
    {"code": "mr", "name": "Marathi", "native_name": "मराठी"},
    {"code": "bn", "name": "Bengali", "native_name": "বাংলা"},
    {"code": "gu", "name": "Gujarati", "native_name": "ગુજરાતી"},
    {"code": "pa", "name": "Punjabi", "native_name": "ਪੰਜਾਬੀ"},
    {"code": "or", "name": "Odia", "native_name": "ଓଡ଼ିଆ"},
    {"code": "ur", "name": "Urdu", "native_name": "اردو"},
]


def get_language_name(code: str) -> str:
    """Get language name by code."""
    for lang in SUPPORTED_LANGUAGES:
        if lang["code"] == code:
            return lang["name"]
    return code


def is_valid_language(code: str) -> bool:
    """Check if language code is valid."""
    return any(lang["code"] == code for lang in SUPPORTED_LANGUAGES)
