import cv2
import numpy as np


class UnsupportedImageError(ValueError):
    pass


class ImageTooLargeError(ValueError):
    pass


def decode_image(data: bytes, *, max_pixels: int) -> np.ndarray:
    image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise UnsupportedImageError("File is not a supported image (PNG, JPEG, TIFF, BMP, WebP)")
    height, width = image.shape[:2]
    if width * height > max_pixels:
        raise ImageTooLargeError(f"Image is {width}x{height} px; the limit is {max_pixels:,} pixels")
    return image
