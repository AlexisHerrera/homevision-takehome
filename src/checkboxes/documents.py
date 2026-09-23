import cv2
import numpy as np
import pypdfium2 as pdfium

PDF_MAGIC = b"%PDF-"


class DocumentError(ValueError):
    pass


class UnsupportedDocumentError(DocumentError):
    pass


class DocumentTooLargeError(DocumentError):
    pass


def load_pages(data: bytes, *, pdf_dpi: int, max_pages: int, max_pixels: int) -> list[np.ndarray]:
    """One image per page. The type is sniffed from the bytes, not the filename."""
    if data.startswith(PDF_MAGIC):
        return _render_pdf(data, dpi=pdf_dpi, max_pages=max_pages, max_pixels=max_pixels)

    image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise UnsupportedDocumentError("File is not a PDF or a supported image (PNG, JPEG, TIFF, BMP, WebP)")
    _check_pixels(image.shape[1], image.shape[0], max_pixels)
    return [image]


def _render_pdf(data: bytes, *, dpi: int, max_pages: int, max_pixels: int) -> list[np.ndarray]:
    try:
        pdf = pdfium.PdfDocument(data)
    except pdfium.PdfiumError as e:
        raise UnsupportedDocumentError(f"Could not open PDF: {e}") from e
    try:
        if len(pdf) > max_pages:
            raise DocumentTooLargeError(f"PDF has {len(pdf)} pages; the limit is {max_pages}")
        scale = dpi / 72  # PDF points are 1/72 inch
        pages = []
        for page in pdf:
            width, height = page.get_size()
            _check_pixels(round(width * scale), round(height * scale), max_pixels)
            pages.append(page.render(scale=scale, grayscale=True).to_numpy().squeeze())
        return pages
    finally:
        pdf.close()


def _check_pixels(width: int, height: int, max_pixels: int) -> None:
    if width * height > max_pixels:
        raise DocumentTooLargeError(f"Page is {width}x{height} px; the limit is {max_pixels:,} pixels")
