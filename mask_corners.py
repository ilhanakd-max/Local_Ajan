from PIL import Image, ImageDraw

def make_rounded_corners(img_path, radius):
    img = Image.open(img_path).convert("RGBA")
    
    # Create a mask with rounded corners
    mask = Image.new("L", img.size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle([(0, 0), img.size], radius=radius, fill=255)
    
    # Apply the mask
    img.putalpha(mask)
    img.save(img_path)
    print(f"Applied {radius}px border radius to {img_path}")

make_rounded_corners('assets/logos/locai_square.png', 12)
make_rounded_corners('assets/logos/locai_horizontal.png', 8)
