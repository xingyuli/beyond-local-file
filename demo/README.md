# Demo Recording Guide

This directory contains scripts for creating and managing the demo GIF for the beyond-local-file project.

## Quick Start

```bash
# 1. Install prerequisites
brew install vhs
uv tool install git+https://github.com/xingyuli/beyond-local-file.git

# 2. Setup demo environment
./demo/setup-demo.sh

# 3. Record the demo
vhs demo/demo.tape

# 4. Optimize the GIF (optional)
./demo/optimize-gif.sh

# 5. View the result
open demo/demo.gif
```

## Prerequisites

**Required:**
- [VHS](https://github.com/charmbracelet/vhs) - Terminal recording tool
- beyond-local-file installed from GitHub

**Optional:**
- [gifsicle](https://www.lcdf.org/gifsicle/) - For GIF optimization (installed by optimize-gif.sh)

```bash
brew install vhs
uv tool install git+https://github.com/xingyuli/beyond-local-file.git
```

## Files

- `demo.tape` - VHS recording script (defines what to record)
- `setup-demo.sh` - Creates demo environment with sample files
- `optimize-gif.sh` - Optimizes GIF file size for GitHub
- `test-commands.sh` - Tests all demo commands before recording
- `demo.gif` - The final demo GIF (committed to repo)

## Demo Content

The demo showcases:

1. **Installation** - `uv tool install` from GitHub
2. **Project Structure** - Show workspace layout
3. **Configuration** - Display config.yml mapping
4. **Sync Command** - Create symlinks automatically
5. **Verification** - Check symlinks in target project
6. **Git Integration** - Show .git/info/exclude entries
7. **Check Command** - Verify sync status

## Customization

Edit `demo/demo.tape` to customize the recording:

```tape
Set FontSize 14          # Adjust font size
Set Width 1400           # Terminal width
Set Height 800           # Terminal height  
Set Theme "Dracula"      # Color theme
Set TypingSpeed 80ms     # Typing animation speed
Set PlaybackSpeed 1.0    # Overall playback speed
```

Available themes: Dracula, Monokai, Nord, Solarized, etc.

## Optimization

The demo GIF should be optimized before committing:

```bash
# Automatic optimization (recommended)
./demo/optimize-gif.sh

# This will:
# - Reduce to 256 colors
# - Apply lossy compression
# - Aim for < 2MB file size
# - Replace original with optimized version
```

**File size guidelines:**
- < 2MB: Excellent for GitHub
- 2-5MB: Acceptable
- \> 5MB: Needs optimization

## Testing

Test all commands before recording:

```bash
chmod +x demo/test-commands.sh
./demo/test-commands.sh
```

This verifies:
- Demo environment setup works
- beyond-local-file is installed
- All commands execute successfully
- Symlinks are created correctly
- Git exclude is updated

## Troubleshooting

**"command not found: beyond-local-file"**
```bash
uv tool install git+https://github.com/xingyuli/beyond-local-file.git
# Ensure ~/.local/bin is in PATH
export PATH="$HOME/.local/bin:$PATH"
```

**"command not found: vhs"**
```bash
brew install vhs
```

**GIF too large**
```bash
# Run optimization
./demo/optimize-gif.sh

# Or manually with more aggressive settings
gifsicle -O3 --colors 128 --lossy=100 demo/demo.gif -o demo/demo-optimized.gif
```

**Demo environment issues**
```bash
# Clean and recreate
rm -rf demo-workspace
./demo/setup-demo.sh
```

## Updating the Demo

When updating the demo:

1. Update `demo.tape` with new commands
2. Test: `./demo/test-commands.sh`
3. Record: `vhs demo/demo.tape`
4. Optimize: `./demo/optimize-gif.sh`
5. Commit: `git add demo/demo.gif && git commit -m "Update demo"`

## Adding to README

Once you have the optimized GIF, add it to the main README.md:

```markdown
## 🎬 Quick Demo

![Demo](demo/demo.gif)

*Watch beyond-local-file in action: install from GitHub, sync files, create symlinks, and manage Git excludes automatically.*
```
