"""
Image Metadata Sanitizer

Strips EXIF/GPS/camera metadata from uploaded images (JPEG, PNG, TIFF)
before S3 storage. Prevents accidental PII exposure via GPS coordinates,
device serial numbers, or owner names embedded in image metadata.

Uses Pillow (PIL) to load the image, discard all metadata, and re-save
with the same quality and dimensions.

Usage:
    from utils.image_sanitizer import strip_image_metadata

    clean_bytes = strip_image_metadata(raw_bytes, "image/jpeg")
"""

import io
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# MIME types we can strip metadata from
_STRIPPABLE_MIMES = {
    "image/jpeg",
    "image/png",
    "image/tiff",
    "image/webp",
    "image/bmp",
}

# Map MIME type to Pillow save format
_MIME_TO_FORMAT = {
    "image/jpeg": "JPEG",
    "image/png": "PNG",
    "image/tiff": "TIFF",
    "image/webp": "WEBP",
    "image/bmp": "BMP",
}


def strip_image_metadata(
    file_bytes: bytes,
    mime_type: str,
    jpeg_quality: int = 95,
) -> bytes:
    """
    Strip EXIF/GPS/camera metadata from an image.

    Loads the image with Pillow, creates a new image with pixel data only
    (no metadata), and re-saves it. Preserves image quality and dimensions.

    Args:
        file_bytes: Raw image bytes.
        mime_type: MIME type of the image (e.g. "image/jpeg").
        jpeg_quality: Quality setting for JPEG re-encoding (1-100).

    Returns:
        Sanitized image bytes with metadata removed. If the image cannot
        be processed (unsupported format, corrupt data, PIL not available),
        returns the original bytes unchanged with a logged warning.
    """
    if not file_bytes:
        return file_bytes

    if mime_type not in _STRIPPABLE_MIMES:
        return file_bytes

    save_format = _MIME_TO_FORMAT.get(mime_type)
    if not save_format:
        return file_bytes

    try:
        from PIL import Image

        # Open the image
        src = Image.open(io.BytesIO(file_bytes))

        # Preserve original mode and size
        original_mode = src.mode
        original_size = src.size

        # Create a new image with the same pixel data but no metadata.
        # Image.copy() does NOT copy EXIF; it returns a clean Image object.
        # However, some formats store metadata outside the EXIF tag, so we
        # explicitly create a brand-new image from pixel data.
        clean = Image.new(original_mode, original_size)
        clean.putdata(list(src.getdata()))

        # Preserve ICC profile if present (needed for correct color rendering,
        # and it does not contain PII)
        icc_profile = src.info.get("icc_profile")

        src.close()

        # Re-save to bytes
        buf = io.BytesIO()
        save_kwargs = {"format": save_format}

        if save_format == "JPEG":
            save_kwargs["quality"] = jpeg_quality
            save_kwargs["optimize"] = True
            # JPEG doesn't support alpha; convert RGBA -> RGB
            if clean.mode in ("RGBA", "LA", "PA"):
                clean = clean.convert("RGB")
            elif clean.mode not in ("RGB", "L"):
                clean = clean.convert("RGB")
            if icc_profile:
                save_kwargs["icc_profile"] = icc_profile

        elif save_format == "PNG":
            save_kwargs["optimize"] = True
            if icc_profile:
                save_kwargs["icc_profile"] = icc_profile

        elif save_format == "TIFF":
            if icc_profile:
                save_kwargs["icc_profile"] = icc_profile

        elif save_format == "WEBP":
            save_kwargs["quality"] = jpeg_quality
            if icc_profile:
                save_kwargs["icc_profile"] = icc_profile

        clean.save(buf, **save_kwargs)
        clean.close()

        result = buf.getvalue()

        # Sanity check: re-encoded image should be non-empty
        if not result:
            logger.warning(
                "Image metadata stripping produced empty output for %s, "
                "returning original",
                mime_type,
            )
            return file_bytes

        logger.debug(
            "Stripped image metadata: %s, %dx%d, %d -> %d bytes",
            mime_type, original_size[0], original_size[1],
            len(file_bytes), len(result),
        )
        return result

    except ImportError:
        logger.warning("Pillow not available, skipping image metadata stripping")
        return file_bytes

    except Exception as e:
        logger.warning(
            "Failed to strip image metadata (%s): %s. "
            "Returning original bytes.",
            mime_type, e,
        )
        return file_bytes


def has_exif_data(file_bytes: bytes) -> bool:
    """
    Check whether an image contains EXIF metadata.

    Useful for auditing/testing. Returns False if PIL is not available
    or the file is not a recognized image.

    Args:
        file_bytes: Raw image bytes.

    Returns:
        True if EXIF data is present.
    """
    try:
        from PIL import Image
        from PIL.ExifTags import Base as ExifBase

        img = Image.open(io.BytesIO(file_bytes))
        exif_data = img.getexif()
        img.close()
        return len(exif_data) > 0
    except Exception as _exc:  # noqa: BLE001
        return False


def get_gps_info(file_bytes: bytes) -> Optional[dict]:
    """
    Extract GPS information from image EXIF data (if present).

    Useful for testing that GPS data was successfully stripped.

    Args:
        file_bytes: Raw image bytes.

    Returns:
        Dict with GPS tags, or None if no GPS data found.
    """
    try:
        from PIL import Image

        img = Image.open(io.BytesIO(file_bytes))
        exif_data = img.getexif()

        # GPS info is stored in IFD tag 0x8825
        GPS_IFD_TAG = 0x8825
        gps_ifd = exif_data.get_ifd(GPS_IFD_TAG)

        img.close()

        if gps_ifd:
            return dict(gps_ifd)
        return None

    except Exception as _exc:  # noqa: BLE001
        return None
