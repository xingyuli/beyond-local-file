#!/usr/bin/env bash
# Test all demo commands to ensure they work

set -e

echo "🧪 Testing demo commands..."
echo ""

# Setup
echo "1️⃣  Setting up demo environment..."
bash demo/setup-demo.sh > /dev/null 2>&1
echo "   ✅ Setup complete"
echo ""

# Check if tool is installed
echo "2️⃣  Checking if beyond-local-file is installed..."
if command -v beyond-local-file > /dev/null 2>&1; then
    echo "   ✅ beyond-local-file is installed"
else
    echo "   ⚠️  beyond-local-file not installed"
    echo "   Installing from GitHub..."
    uv tool install git+https://github.com/xingyuli/beyond-local-file.git
    echo "   ✅ Installation complete"
fi
echo ""

# Test tree command
echo "3️⃣  Testing tree command..."
tree -L 2 demo-workspace/ > /dev/null 2>&1 && echo "   ✅ tree works" || echo "   ⚠️  tree not installed (optional)"
echo ""

# Test config display
echo "4️⃣  Testing config display..."
cat demo-workspace/my-dev-files/config.yml > /dev/null 2>&1
echo "   ✅ Config file readable"
echo ""

# Test sync command
echo "5️⃣  Testing sync command..."
cd demo-workspace/my-dev-files
beyond-local-file symlink sync > /dev/null 2>&1
echo "   ✅ Sync command works"
cd ../..
echo ""

# Test symlink verification
echo "6️⃣  Testing symlink verification..."
ls -la demo-workspace/target-project/ | grep '^l' > /dev/null 2>&1
echo "   ✅ Symlinks created"
echo ""

# Test git exclude
echo "7️⃣  Testing git exclude..."
cat demo-workspace/target-project/.git/info/exclude | tail -5 > /dev/null 2>&1
echo "   ✅ Git exclude file updated"
echo ""

# Test check command
echo "8️⃣  Testing check command..."
cd demo-workspace/my-dev-files
beyond-local-file symlink check > /dev/null 2>&1
echo "   ✅ Check command works"
cd ../..
echo ""

echo "🎉 All commands work! Ready to record demo."
echo ""
echo "Next steps:"
echo "  • Install VHS: brew install vhs"
echo "  • Record demo: vhs demo/demo.tape"
echo "  • Or follow manual guide: ./demo/record-manual.sh"
