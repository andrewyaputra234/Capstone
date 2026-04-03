#!/usr/bin/env python3
"""Debug image extraction and display in questions."""

import sys
import os
sys.path.insert(0, 'src')

from agent_a3_dialogue import DialogueManager
from pathlib import Path

print("=" * 60)
print("DEBUGGING IMAGE DISPLAY")
print("=" * 60)

# Test the image extraction
dm = DialogueManager(subject='PSLE_Math')

print(f"\nPDF Path: {dm.pdf_path}")
print(f"PDF Exists: {os.path.exists(dm.pdf_path) if dm.pdf_path else False}")
print(f"\nExtracted {len(dm.page_images)} page images:")
for page, img_path in sorted(dm.page_images.items())[:3]:
    exists = os.path.exists(img_path)
    print(f"  Page {page}: {img_path} (exists: {exists})")

# Extract questions with images
print("\n" + "=" * 60)
print("EXTRACTING QUESTIONS WITH IMAGES")
print("=" * 60)
questions = dm.extract_questions_from_document(num_questions=5)

print(f"\nExtracted {len(questions)} questions:\n")
for i, q in enumerate(questions, 1):
    img = q.get('image_path')
    exists = os.path.exists(img) if img else False
    print(f"Q{i}: {q.get('text')[:60]}...")
    print(f"     image_path: {img}")
    print(f"     exists: {exists}")
    print()

# Test fallback
print("=" * 60)
print("TESTING FALLBACK LOGIC")
print("=" * 60)
fallback_img = dm.get_question_image("what is the pie chart")
print(f"Fallback image for 'pie chart': {fallback_img}")
if fallback_img:
    print(f"Fallback exists: {os.path.exists(fallback_img)}")
