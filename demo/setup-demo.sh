#!/usr/bin/env bash
# Setup demo environment for beyond-local-file

set -e

DEMO_DIR="demo-workspace"

echo "🧹 Cleaning up old demo environment..."
rm -rf "$DEMO_DIR"

echo "📁 Creating demo directory structure..."
mkdir -p "$DEMO_DIR"
cd "$DEMO_DIR"

# Create managed projects directory
mkdir -p my-dev-files/project-a
mkdir -p my-dev-files/project-a/local-file
mkdir -p my-dev-files/project-a/.qoder

# Create some example files
cat > my-dev-files/project-a/local-file/README.md << 'EOF'
# Local Development Files

This directory contains local-only development files.
EOF

cat > my-dev-files/project-a/.qoder/rules.md << 'EOF'
# Project Rules

- Use Python 3.13+
- Follow PEP 8
EOF

cat > my-dev-files/project-a/test.http << 'EOF'
### Test API
GET https://api.example.com/users
EOF

# Create config file
cat > my-dev-files/config.yml << EOF
project-a: $(pwd)/target-project
EOF

# Create target project with git repo
mkdir -p target-project
cd target-project
git init -q
git config user.name "Demo User"
git config user.email "demo@example.com"
echo "# Target Project" > README.md
git add README.md
git commit -q -m "Initial commit"
cd ..

cd ..

echo "✅ Demo environment created at: $DEMO_DIR"
echo ""
echo "📝 Structure:"
tree -L 3 -a "$DEMO_DIR" 2>/dev/null || find "$DEMO_DIR" -type f
echo ""
echo "🎬 To record demo:"
echo "   vhs demo/demo.tape"
echo ""
echo "💡 The demo uses 'uv run --directory' to run the local version"
echo "   This works even if beyond-local-file is not installed globally"
