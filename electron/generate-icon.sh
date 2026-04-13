#!/usr/bin/env bash
# Generate macOS .icns icon from icon.svg
# Requires: sips (built into macOS) or ImageMagick (convert)
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

ICONSET="icon.iconset"
mkdir -p "$ICONSET"

# Try rsvg-convert first, then sips, then convert (ImageMagick)
render_png() {
    local size=$1
    local out=$2
    if command -v rsvg-convert &>/dev/null; then
        rsvg-convert -w "$size" -h "$size" icon.svg -o "$out"
    elif command -v sips &>/dev/null; then
        # sips can't read SVG; we need a PNG intermediate — skip if no other tool
        if command -v convert &>/dev/null; then
            convert -background none -resize "${size}x${size}" icon.svg "$out"
        else
            echo "Error: Install librsvg (brew install librsvg) or ImageMagick (brew install imagemagick)"
            exit 1
        fi
    elif command -v convert &>/dev/null; then
        convert -background none -resize "${size}x${size}" icon.svg "$out"
    else
        echo "Error: Install librsvg (brew install librsvg) or ImageMagick (brew install imagemagick)"
        exit 1
    fi
}

# Generate all required sizes for .icns
for size in 16 32 64 128 256 512 1024; do
    echo "  Generating ${size}x${size}..."
    render_png $size "$ICONSET/icon_${size}x${size}.png"
done

# macOS iconutil expects specific naming
cp "$ICONSET/icon_16x16.png"     "$ICONSET/icon_16x16.png"
cp "$ICONSET/icon_32x32.png"     "$ICONSET/icon_16x16@2x.png"
cp "$ICONSET/icon_32x32.png"     "$ICONSET/icon_32x32.png"
cp "$ICONSET/icon_64x64.png"     "$ICONSET/icon_32x32@2x.png"
cp "$ICONSET/icon_128x128.png"   "$ICONSET/icon_128x128.png"
cp "$ICONSET/icon_256x256.png"   "$ICONSET/icon_128x128@2x.png"
cp "$ICONSET/icon_256x256.png"   "$ICONSET/icon_256x256.png"
cp "$ICONSET/icon_512x512.png"   "$ICONSET/icon_256x256@2x.png"
cp "$ICONSET/icon_512x512.png"   "$ICONSET/icon_512x512.png"
cp "$ICONSET/icon_1024x1024.png" "$ICONSET/icon_512x512@2x.png"

# Remove the non-standard sizes
rm -f "$ICONSET/icon_64x64.png" "$ICONSET/icon_1024x1024.png"

if command -v iconutil &>/dev/null; then
    iconutil -c icns "$ICONSET" -o icon.icns
    echo "Generated icon.icns"
else
    echo "iconutil not available (macOS only). Iconset prepared in $ICONSET/"
    echo "Run on macOS: iconutil -c icns $ICONSET -o icon.icns"
fi

rm -rf "$ICONSET"
