#!/usr/bin/env bash
# Optimize demo GIF for GitHub

set -e

INPUT="demo/demo.gif"
OUTPUT="demo/demo-optimized.gif"

if [ ! -f "$INPUT" ]; then
    echo "❌ Error: $INPUT not found"
    echo "Run 'vhs demo/demo.tape' first"
    exit 1
fi

ORIGINAL_SIZE=$(du -h "$INPUT" | cut -f1)
echo "📊 Original size: $ORIGINAL_SIZE"

# Check if gifsicle is installed
if ! command -v gifsicle &> /dev/null; then
    echo "📦 Installing gifsicle..."
    brew install gifsicle
fi

echo "🔧 Optimizing GIF..."

# Optimize with gifsicle
# -O3: maximum optimization
# --colors 256: reduce to 256 colors
# --lossy=80: lossy compression (adjust 0-200, higher = more compression)
gifsicle -O3 --colors 256 --lossy=80 "$INPUT" -o "$OUTPUT"

OPTIMIZED_SIZE=$(du -h "$OUTPUT" | cut -f1)
echo "✅ Optimized size: $OPTIMIZED_SIZE"

# Calculate reduction
ORIGINAL_BYTES=$(stat -f%z "$INPUT" 2>/dev/null || stat -c%s "$INPUT")
OPTIMIZED_BYTES=$(stat -f%z "$OUTPUT" 2>/dev/null || stat -c%s "$OUTPUT")
REDUCTION=$(echo "scale=1; (1 - $OPTIMIZED_BYTES / $ORIGINAL_BYTES) * 100" | bc)

echo "📉 Size reduction: ${REDUCTION}%"
echo ""

if (( $(echo "$OPTIMIZED_BYTES < 2000000" | bc -l) )); then
    echo "✅ Size is good for GitHub (< 2MB)"
    echo "   Replacing original with optimized version..."
    mv "$OUTPUT" "$INPUT"
    echo "   Done! Use demo/demo.gif in your README"
elif (( $(echo "$OPTIMIZED_BYTES < 5000000" | bc -l) )); then
    echo "⚠️  Size is acceptable (< 5MB) but could be better"
    echo "   Options:"
    echo "   1. Use optimized version: mv $OUTPUT $INPUT"
    echo "   2. Further reduce: gifsicle -O3 --colors 128 --lossy=100 $INPUT -o $OUTPUT"
    echo "   3. Convert to video: ffmpeg -i $INPUT demo/demo.mp4"
else
    echo "❌ Size is too large (> 5MB)"
    echo "   Recommendations:"
    echo "   1. Reduce recording length"
    echo "   2. Use more aggressive compression"
    echo "   3. Convert to MP4 video instead"
    echo "   4. Host on vhs.charm.sh: vhs publish $INPUT"
fi
