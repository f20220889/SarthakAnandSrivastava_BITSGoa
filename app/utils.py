import requests
from pdf2image import convert_from_bytes
from io import BytesIO
import base64

def download_file(url: str) -> bytes:
    response = requests.get(url)
    response.raise_for_status()
    return response.content

def process_document(file_content: bytes, url: str) -> list[str]:
    """
    Returns a list of base64 encoded strings (images).
    Handles both PDF and Image URLs.
    """
    images_base64 = []
    
    # Check if PDF based on extension or header
    if url.lower().endswith('.pdf') or file_content.startswith(b'%PDF'):
        # Convert PDF to images (300 DPI for better OCR)
        images = convert_from_bytes(file_content, dpi=300, fmt='jpeg')
        for img in images:
            buffered = BytesIO()
            img.save(buffered, format="JPEG")
            img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
            images_base64.append(img_str)
    else:
        # It's an image
        img_str = base64.b64encode(file_content).decode("utf-8")
        images_base64.append(img_str)
        
    return images_base64