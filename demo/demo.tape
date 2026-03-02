# VHS documentation: https://github.com/charmbracelet/vhs
#
# This tape demonstrates the core functionality of beyond-local-file

# Output settings
Output demo/demo.gif
Set FontSize 14
Set Width 1400
Set Height 800
Set Theme "Dracula"
Set Padding 20
Set TypingSpeed 80ms
Set PlaybackSpeed 1.0

# Show the project structure
Type "# Beyond Local File - Demo"
Sleep 1s
Enter
Type "# Manage local dev files across projects with symlinks"
Sleep 2s
Enter 2

# Install the tool from GitHub
Type "# First, install from GitHub"
Sleep 1s
Enter
Type "uv tool install git+https://github.com/xingyuli/beyond-local-file.git"
Sleep 500ms
Enter
Sleep 8s
Enter

# Show directory structure
Type "# Show the workspace structure"
Sleep 1s
Enter
Type "tree -aL 3 demo-workspace/"
Sleep 500ms
Enter
Sleep 3s
Enter

# Show config file
Type "# Configuration maps projects to targets"
Sleep 1s
Enter
Type "cat demo-workspace/my-dev-files/config.yml"
Sleep 500ms
Enter
Sleep 2.5s
Enter

# Navigate to managed projects directory
Type "cd demo-workspace/my-dev-files"
Sleep 500ms
Enter
Sleep 1s

# Run sync command
Type "# Sync creates symlinks automatically"
Sleep 1s
Enter
Type "beyond-local-file symlink sync"
Sleep 500ms
Enter
Sleep 5s
Enter

# Check the results
Type "# Verify symlinks were created"
Sleep 1s
Enter
Type "cd ../target-project"
Sleep 500ms
Enter
Sleep 500ms
Type "ls -la | grep '^l'"
Sleep 500ms
Enter
Sleep 3s
Enter

# Show git exclude
Type "# Git excludes added automatically"
Sleep 1s
Enter
Type "cat .git/info/exclude | tail -5"
Sleep 500ms
Enter
Sleep 2.5s
Enter

# Run check command
Type "# Check status anytime"
Sleep 1s
Enter
Type "cd ../my-dev-files"
Sleep 500ms
Enter
Type "beyond-local-file symlink check"
Sleep 500ms
Enter
Sleep 4s
Enter

# End
Type "# ✨ Done! Symlinks + Git excludes configured automatically"
Sleep 3s
