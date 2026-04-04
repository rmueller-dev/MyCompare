"""
Pixel-level image comparison for embedded images in DOCX/PPTX files.
Extracts images from Office documents and compares them using Pillow.
Labels are in German to match the rest of the application.
"""
import base64
import os
import zipfile
from io import BytesIO

from PIL import Image, ImageChops, ImageDraw


def extract_images(filepath, file_type):
    """
    Extract all embedded images from a DOCX or PPTX file.

    Args:
        filepath: Path to the document file.
        file_type: 'docx' or 'pptx'.

    Returns:
        List of dicts: {name, data_bytes, content_type, context}
        - name: image filename (e.g. 'image1.png')
        - data_bytes: raw bytes of the image
        - content_type: MIME type (e.g. 'image/png')
        - context: location context ('body', 'header', slide number, etc.)
    """
    if file_type not in ('docx', 'pptx'):
        return []

    images = []
    media_prefix = 'word/media/' if file_type == 'docx' else 'ppt/media/'

    # Extensions that Pillow can handle for pixel comparison
    SUPPORTED_EXTS = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff', '.tif'}

    content_type_map = {
        '.png': 'image/png',
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.gif': 'image/gif',
        '.bmp': 'image/bmp',
        '.tiff': 'image/tiff',
        '.tif': 'image/tiff',
        '.emf': 'image/x-emf',
        '.wmf': 'image/x-wmf',
        '.svg': 'image/svg+xml',
    }

    try:
        with zipfile.ZipFile(filepath, 'r') as zf:
            for entry in zf.namelist():
                if not entry.startswith(media_prefix):
                    continue

                ext = os.path.splitext(entry)[1].lower()
                content_type = content_type_map.get(ext, 'application/octet-stream')

                # Skip vector formats that Pillow cannot handle
                if ext not in SUPPORTED_EXTS:
                    continue

                name = os.path.basename(entry)
                data_bytes = zf.read(entry)

                # Determine context based on file path structure
                if file_type == 'docx':
                    context = 'body'
                else:
                    # For PPTX, all media is in ppt/media/; context set generically
                    context = 'Folie'

                images.append({
                    'name': name,
                    'data_bytes': data_bytes,
                    'content_type': content_type,
                    'context': context,
                })
    except (zipfile.BadZipFile, Exception):
        return []

    return images


def _image_from_bytes(data_bytes):
    """Load a PIL Image from raw bytes. Returns None on failure."""
    try:
        img = Image.open(BytesIO(data_bytes))
        img = img.convert('RGBA')
        return img
    except Exception:
        return None


def _compute_similarity(img_a, img_b):
    """
    Compute pixel-level similarity percentage between two images.
    Images are resized to the same dimensions if they differ.
    Returns (similarity_pct, diff_image) where diff_image is an RGBA PIL Image.
    """
    # Resize to common dimensions (use the larger of each dimension)
    w = max(img_a.width, img_b.width)
    h = max(img_a.height, img_b.height)

    a = img_a.resize((w, h), Image.LANCZOS)
    b = img_b.resize((w, h), Image.LANCZOS)

    # Compute absolute pixel difference
    diff = ImageChops.difference(a, b)

    # Count identical pixels efficiently using getcolors with a large maxcolors
    # A pixel is identical when all channels are 0 in the diff image.
    # We use the histogram approach: sum up pixels where R=G=B=0 (and any A).
    # Convert diff to RGB to ignore alpha for comparison purposes.
    diff_rgb = diff.convert('RGB')
    diff_data = list(diff_rgb.getdata())
    total_pixels = w * h
    identical = sum(1 for r, g, b in diff_data if r == 0 and g == 0 and b == 0)
    similarity_pct = round((identical / total_pixels) * 100, 1) if total_pixels > 0 else 100.0

    # Generate visual diff overlay: original A with red highlights where pixels differ
    # Create a red highlight mask from the diff
    red_overlay = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    red_pixels = red_overlay.load()
    diff_pixels = diff_rgb.load()

    for y in range(h):
        for x in range(w):
            r, g, b = diff_pixels[x, y]
            if r != 0 or g != 0 or b != 0:
                red_pixels[x, y] = (255, 0, 0, 128)

    # Composite the red overlay onto the original
    diff_image = Image.alpha_composite(a, red_overlay)

    return similarity_pct, diff_image


def _image_to_base64(img, fmt='PNG'):
    """Convert a PIL Image to a base64-encoded string."""
    buf = BytesIO()
    img.save(buf, format=fmt)
    return base64.b64encode(buf.getvalue()).decode('utf-8')


def compare_images(images_a, images_b):
    """
    Compare two lists of extracted images (from two document versions).

    Matching is done by image filename. Images present in only one version
    are reported as added/removed. Images in both are compared pixel-by-pixel.

    Args:
        images_a: List of image dicts from version A (old).
        images_b: List of image dicts from version B (new).

    Returns:
        List of image change dicts:
        {
            name: str,
            type: 'added' | 'removed' | 'changed' | 'unchanged',
            similarity_pct: float (0-100),
            diff_image_base64: str or None,
            context: str,
        }
    """
    map_a = {img['name']: img for img in images_a}
    map_b = {img['name']: img for img in images_b}

    all_names = sorted(set(list(map_a.keys()) + list(map_b.keys())))
    results = []

    for name in all_names:
        in_a = name in map_a
        in_b = name in map_b

        if in_a and not in_b:
            results.append({
                'name': name,
                'type': 'removed',
                'similarity_pct': 0.0,
                'diff_image_base64': None,
                'context': map_a[name].get('context', ''),
            })
        elif in_b and not in_a:
            results.append({
                'name': name,
                'type': 'added',
                'similarity_pct': 0.0,
                'diff_image_base64': None,
                'context': map_b[name].get('context', ''),
            })
        else:
            # Both present -- compare pixel data
            img_a = _image_from_bytes(map_a[name]['data_bytes'])
            img_b = _image_from_bytes(map_b[name]['data_bytes'])

            if img_a is None or img_b is None:
                # Cannot decode one of the images; report as changed
                results.append({
                    'name': name,
                    'type': 'changed',
                    'similarity_pct': 0.0,
                    'diff_image_base64': None,
                    'context': map_a[name].get('context', ''),
                })
                continue

            # Quick check: if raw bytes are identical, skip pixel comparison
            if map_a[name]['data_bytes'] == map_b[name]['data_bytes']:
                results.append({
                    'name': name,
                    'type': 'unchanged',
                    'similarity_pct': 100.0,
                    'diff_image_base64': None,
                    'context': map_a[name].get('context', ''),
                })
                continue

            similarity_pct, diff_image = _compute_similarity(img_a, img_b)

            if similarity_pct >= 100.0:
                change_type = 'unchanged'
                diff_b64 = None
            else:
                change_type = 'changed'
                diff_b64 = _image_to_base64(diff_image)

            results.append({
                'name': name,
                'type': change_type,
                'similarity_pct': similarity_pct,
                'diff_image_base64': diff_b64,
                'context': map_a[name].get('context', ''),
            })

    return results
