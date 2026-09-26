from io import BytesIO

import cv2
import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None  # decode_image enforces its own limit

# Checked against the file's contents; the filename and declared content type are ignored.
FORMATS = ("PNG", "JPEG", "TIFF", "BMP", "WEBP")
UNSUPPORTED_MESSAGE = "File is not a supported image (PNG, JPEG, TIFF, BMP, WebP)"


class UnsupportedImageError(ValueError):
    pass


class ImageTooLargeError(ValueError):
    pass


def decode_image(data: bytes, *, max_pixels: int) -> np.ndarray:
    try:
        with Image.open(BytesIO(data), formats=FORMATS) as header:
            width, height = header.size
    except OSError as e:
        raise UnsupportedImageError(UNSUPPORTED_MESSAGE) from e

    if width * height > max_pixels:
        raise ImageTooLargeError(f"Image is {width}x{height} px; the limit is {max_pixels:,} pixels")

    image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise UnsupportedImageError(UNSUPPORTED_MESSAGE)
    return image
