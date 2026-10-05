from PIL import Image
import os

img_path = '/home/ilhan/.gemini/antigravity/brain/aa450360-fe60-407d-8fe0-e44f6e7c05f6/.user_uploaded/media_1791199459473.png'
img = Image.open(img_path)

os.makedirs('assets/logos', exist_ok=True)

# We need to find the exact bounding boxes for the left and right rounded rectangles.
# They are dark blocks on a light checkerboard.
# We can find them programmatically.
pixels = img.load()
width, height = img.size

def find_dark_block(start_x, end_x):
    min_x, max_x = width, 0
    min_y, max_y = height, 0
    found = False
    
    for x in range(start_x, end_x):
        for y in range(height):
            r, g, b, _ = pixels[x, y]
            # Dark background is very dark blue/grey
            if r < 40 and g < 40 and b < 50:
                min_x = min(min_x, x)
                max_x = max(max_x, x)
                min_y = min(min_y, y)
                max_y = max(max_y, y)
                found = True
    
    if found:
        return (min_x, min_y, max_x, max_y)
    return None

left_box = find_dark_block(0, 300)
right_box = find_dark_block(700, width)

print("Left Box:", left_box)
print("Right Box:", right_box)

if left_box:
    # Expand by 1 pixel to ensure we don't cut into the anti-aliased border, wait, if we expand we might get the checkerboard.
    # We will crop exactly at the box.
    left_img = img.crop(left_box)
    # The corners are rounded and might have checkerboard pixels on the outside. 
    # Let's clean the corners by making them transparent.
    left_img.save('assets/logos/locai_square.png')

if right_box:
    right_img = img.crop(right_box)
    right_img.save('assets/logos/locai_horizontal.png')
