"""Single source of truth for allowed upload MIME types."""
from types import MappingProxyType

_ALLOWED = {
    "application/pdf":          ({"pdf"},         50 * 1024 * 1024),
    "image/jpeg":               ({"jpg", "jpeg"}, 25 * 1024 * 1024),
    "image/png":                ({"png"},         25 * 1024 * 1024),
    "image/tiff":               ({"tif", "tiff"}, 50 * 1024 * 1024),
    "image/gif":                ({"gif"},         25 * 1024 * 1024),
    "image/bmp":                ({"bmp"},         25 * 1024 * 1024),
    "image/webp":               ({"webp"},        25 * 1024 * 1024),
}

ALLOWED_MIME_TYPES = frozenset(_ALLOWED.keys())
MAX_BYTES_BY_MIME = MappingProxyType({k: v[1] for k, v in _ALLOWED.items()})
EXTENSIONS_BY_MIME = MappingProxyType({k: v[0] for k, v in _ALLOWED.items()})


def is_allowed(mime: str) -> bool:
    return mime in ALLOWED_MIME_TYPES


def max_bytes_for(mime: str) -> int:
    return MAX_BYTES_BY_MIME.get(mime, 0)
