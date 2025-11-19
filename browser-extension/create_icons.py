#!/usr/bin/env python3
"""Create placeholder icons for browser extension"""
from PIL import Image, ImageDraw, ImageFont

def create_icon(size, text, filename):
    # Create image with CRM color
    img = Image.new('RGB', (size, size), '#218D8D')
    draw = ImageDraw.Draw(img)

    # Add text
    font_size = size // 3
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", font_size)
    except:
        font = ImageFont.load_default()

    # Center text
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]

    x = (size - text_width) // 2
    y = (size - text_height) // 2

    draw.text((x, y), text, fill='white', font=font)

    # Save
    img.save(filename, 'PNG')
    print(f"Created {filename}")

# Create icons
create_icon(16, "M", "icon16.png")
create_icon(48, "MG", "icon48.png")
create_icon(128, "MG", "icon128.png")
print("✅ All icons created!")
