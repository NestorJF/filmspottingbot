"""Normalize subtitle language codes so "es", "spa", "es-ES" and "Spanish" all match."""

from functools import lru_cache

from babelfish import Error as BabelfishError
from babelfish import Language


@lru_cache(maxsize=256)
def normalize_language(code: str | None) -> str | None:
    """Return the ISO 639-1 code (or ISO 639-3 when there is none); unknown codes are just lowercased."""
    if not code or not code.strip():
        return None
    code = code.strip()
    if code.lower() == "und":  # Matroska's "undetermined"
        return None
    parsers = (Language.fromietf, Language.fromalpha3b, Language.fromalpha3t, Language.fromname)
    for parse in parsers:
        try:
            language = parse(code if parse is not Language.fromname else code.capitalize())
        except (BabelfishError, ValueError, KeyError):
            continue
        try:
            return language.alpha2
        except BabelfishError:  # no two-letter code (e.g. "yue")
            return language.alpha3
    return code.lower()
