"""
Agent: Image Extractor
Extracts images and pages from PDF documents for visual question reference.
Converts PDF pages to images (PNG) for display in assessment.
"""

import os
from pathlib import Path
from typing import List, Dict, Optional


def extract_pdf_pages_as_images(
    pdf_path: str,
    output_dir: str,
    dpi: int = 150
) -> Dict[int, str]:
    """
    Extract PDF pages as images (PNG format) using PyMuPDF (fitz).
    
    Args:
        pdf_path: Path to PDF file
        output_dir: Directory to save images
        dpi: Resolution (150 = good balance of quality/size)
        
    Returns:
        Dict mapping page number -> image file path
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        print("ERROR: PyMuPDF not installed.")
        print("Install with: pip install PyMuPDF")
        return {}
    
    # Create output directory
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    try:
        # Open PDF
        print(f"Converting PDF to images: {pdf_path}")
        doc = fitz.open(pdf_path)
        
        page_images = {}
        zoom = dpi / 72  # Convert DPI to zoom factor (72 is default)
        
        for page_num in range(len(doc)):
            # Get page and render to image
            page = doc[page_num]
            mat = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=mat)
            
            # Save as PNG
            image_path = os.path.join(output_dir, f"page_{page_num + 1}.png")
            pix.save(image_path)
            page_images[page_num + 1] = image_path
            print(f"  ✓ Saved page {page_num + 1} -> {image_path}")
        
        doc.close()
        print(f"✓ Extracted {len(page_images)} pages from PDF\n")
        return page_images
        
    except Exception as e:
        print(f"ERROR extracting PDF pages: {e}")
        return {}


def extract_pdf_images_only(
    pdf_path: str,
    output_dir: str
) -> List[str]:
    """
    Extract only embedded images from PDF (not page screenshots).
    More efficient but may miss images in some PDFs.
    
    Args:
        pdf_path: Path to PDF file
        output_dir: Directory to save images
        
    Returns:
        List of extracted image file paths
    """
    try:
        import PyPDF2
    except ImportError:
        print("ERROR: PyPDF2 not installed.")
        print("Install with: pip install PyPDF2")
        return []
    
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    try:
        print(f"Extracting embedded images from: {pdf_path}")
        image_paths = []
        
        with open(pdf_path, "rb") as f:
            pdf_reader = PyPDF2.PdfReader(f)
            
            for page_num in range(len(pdf_reader.pages)):
                page = pdf_reader.pages[page_num]
                
                if "/XObject" in page["/Resources"]:
                    xObject = page["/Resources"]["/XObject"].get_object()
                    
                    image_count = 0
                    for obj in xObject:
                        if xObject[obj]["/Subtype"] == "/Image":
                            try:
                                size = (xObject[obj]["/Width"], xObject[obj]["/Height"])
                                data = xObject[obj].get_data()
                                
                                # Save as image file
                                image_path = os.path.join(
                                    output_dir,
                                    f"page_{page_num + 1}_image_{image_count}.png"
                                )
                                
                                # Create image from raw data
                                from PIL import Image
                                image = Image.new("RGB", size)
                                image.frombytes("RGB", size, data)
                                image.save(image_path)
                                
                                image_paths.append(image_path)
                                image_count += 1
                                print(f"  ✓ Extracted image from page {page_num + 1}")
                            except Exception as e:
                                print(f"  ⚠ Could not extract image: {e}")
        
        print(f"✓ Extracted {len(image_paths)} images\n")
        return image_paths
        
    except Exception as e:
        print(f"ERROR: {e}")
        return []


def get_page_for_question(question_text: str, pdf_path: str) -> Optional[int]:
    """
    Determine which PDF page a question comes from.
    Uses text matching to find the question in the PDF.
    Falls back to page 1 if not found.
    
    Args:
        question_text: The question text to find
        pdf_path: Path to PDF file
        
    Returns:
        Page number (1-indexed), defaults to 1 if not found
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        return 1  # Default to page 1
    
    try:
        doc = fitz.open(pdf_path)
        
        # Search first 100 characters of question
        search_text = question_text[:100].lower()
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            page_text = page.get_text().lower()
            
            # Check if any part of the search text is in the page
            if search_text[:30] in page_text:
                doc.close()
                return page_num + 1  # 1-indexed
        
        doc.close()
        return 1  # Default to page 1 if not found
        
    except Exception as e:
        print(f"⚠️ Could not find question page: {e}")
        return 1  # Default to page 1 on error


if __name__ == "__main__":
    # Test extraction
    test_pdf = "data/input/PSLE_Math/PSLE-standard-math-paper-1-2-questions-with-answers-2024.pdf"
    
    if os.path.exists(test_pdf):
        output_dir = f"data/PSLE_Math_images"
        page_images = extract_pdf_pages_as_images(test_pdf, output_dir)
        print(f"Extracted {len(page_images)} pages")
    else:
        print(f"Test PDF not found: {test_pdf}")
