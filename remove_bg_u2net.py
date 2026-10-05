from PIL import Image
import os
from rembg import remove, new_session

img_path = '/home/ilhan/.gemini/antigravity/brain/aa450360-fe60-407d-8fe0-e44f6e7c05f6/.user_uploaded/media_1791199459473.png'
img = Image.open(img_path)

# Let's crop the center logo (shield + text)
center_img = img.crop((250, 50, 780, 550))

print("Creating session for u2net...")
session = new_session("u2net")

print("Removing background...")
output_img = remove(center_img, session=session)

# Save to assets
output_img.save('assets/logos/locai_center_transparent.png')
print("Background removed successfully.")
