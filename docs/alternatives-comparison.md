# Alternatives Comparison

This document provides detailed comparisons between `beyond-local-file` and similar tools to help you choose the right solution for your needs.

## Quick Summary

- **Use GNU Stow** for managing dotfiles in `$HOME` with a simple, lightweight approach
- **Use chezmoi** for managing dotfiles across multiple machines with templating, encryption, and password manager integration
- **Use beyond-local-file** for managing local development files across multiple projects with automatic Git exclude handling

---

## GNU Stow

### What is GNU Stow?

**GNU Stow** is a dotfile organizer that uses a package-based approach to manage configuration files. Each "package" (like `vim/` or `zsh/`) mirrors your `$HOME` directory structure, and Stow creates symlinks from the stow directory to your home directory.

### Core Concepts

- **Stow directory:** Central location containing packages (e.g., `~/dotfiles/`)
- **Target directory:** Where symlinks are created (typically `$HOME`)
- **Packages:** Subdirectories that mirror the target structure (e.g., `vim/`, `zsh/`)
- **Tree folding:** Minimizes symlinks by linking directories instead of individual files

### Typical Workflow

```bash
# Create package structure
mkdir -p ~/dotfiles/vim
mv ~/.vimrc ~/dotfiles/vim/.vimrc

# Create symlinks
cd ~/dotfiles
stow vim

# Result: ~/.vimrc -> ~/dotfiles/vim/.vimrc
```

### Configuration Approach

Stow uses CLI parameters to define relationships:

```bash
stow -d ~/dotfiles -t ~ vim zsh git
```

You can create a `.stowrc` file for convenience:

```
--dir=~/dotfiles
--target=~
--dotfiles
--ignore='README.*'
--ignore='\.git.*'
```

### Strengths

- Simple and lightweight
- Minimal learning curve
- Works well for dotfiles in `$HOME`
- Mature and stable (Perl-based)
- Good for version-controlling dotfiles with Git
- Native support on Unix-like systems (Linux, macOS)

### Limitations

- Designed primarily for single target directory (`$HOME`)
- Configuration via CLI parameters can be verbose
- No built-in Git exclude management
- Symlinks only (no copy mode)
- Manual management of `.gitignore` files
- Limited Windows support (requires MSYS2 with special configuration)

### When to Use Stow

- Managing personal dotfiles (`.bashrc`, `.vimrc`, `.gitconfig`)
- Simple setup with minimal features needed
- Single target directory (typically `$HOME`)
- You prefer CLI-based configuration

---

## chezmoi

### What is chezmoi?

**chezmoi** is a comprehensive dotfiles manager designed to manage personal configuration files across multiple diverse machines. It uses a source directory (typically a Git repository) that defines the desired state of your dotfiles, with powerful templating and encryption features.

### Core Concepts

- **Source directory:** Contains the desired state of dotfiles (typically `~/.local/share/chezmoi/`)
- **Target directory:** Where files are applied (typically `$HOME`)
- **Templates:** Go templates for machine-specific customization
- **Encryption:** Built-in support for age and GPG
- **Password managers:** Integration with 1Password, Bitwarden, LastPass, etc.

### Typical Workflow

```bash
# Initialize chezmoi
chezmoi init

# Add a dotfile
chezmoi add ~/.bashrc

# Edit in source directory
chezmoi edit ~/.bashrc

# Preview changes
chezmoi diff

# Apply changes
chezmoi apply

# Sync via Git
chezmoi cd
git add .
git commit -m "Update bashrc"
git push
```

### Configuration Approach

chezmoi uses a source directory with templates and configuration files:

```toml
# ~/.config/chezmoi/chezmoi.toml
[data]
    email = "user@example.com"
    
[encryption]
    type = "age"
```

Templates allow machine-specific customization:

```bash
# dot_gitconfig.tmpl
[user]
    email = "{{ .email }}"
    name = "{{ .name }}"
```

### Strengths

- Comprehensive feature set for dotfiles management
- Powerful templating for machine-specific configurations
- Built-in encryption for secrets
- Password manager integration
- Git-based workflow for syncing across machines
- Excellent cross-platform support (Linux, macOS, Windows, FreeBSD, OpenBSD, Termux)
- Diff/merge capabilities
- Declarative and idempotent
- Single binary, easy to install

### Limitations

- Steeper learning curve due to feature richness
- Designed for `$HOME` dotfiles, not per-project files
- Requires understanding of Go templates for advanced use
- More complex than needed for simple use cases
- Focused on version-controlled dotfiles

### When to Use chezmoi

- Managing dotfiles across multiple machines with different configurations
- Need templating for OS-specific or machine-specific customization
- Managing secrets (API keys, tokens) with encryption
- Integration with password managers
- Complex dotfiles setup with many customizations

---

## beyond-local-file

### What is beyond-local-file?

**beyond-local-file** is a lightweight tool for managing local development files across multiple projects. It's designed for files that are useful in your project directory but shouldn't be committed to Git.

### Core Concepts

- **Managed projects:** Central location containing your local dev files
- **Target projects:** Your actual project directories where files are synced
- **Subpath selection:** Choose specific files/directories to sync
- **Copy strategy:** Physical copies for tools that don't follow symlinks
- **Git exclude automation:** Automatically updates `.git/info/exclude`

### Typical Workflow

```bash
# Create config.yml in managed projects directory
cat > config.yml << 'EOF'
project-a: /Users/username/workspace/project-a
project-b: /Users/username/workspace/project-b
EOF

# Sync files
blf link sync

# Check status
blf link check
```

### Configuration Approach

Centralized `config.yml` manages all project mappings:

```yaml
# Simple mapping
project-a: /Users/username/workspace/project-a

# Multiple targets
project-b:
  - /Users/username/workspace/project-b
  - /Users/username/workspace/project-b-fork

# Selective subpaths
project-c:
  target: /Users/username/workspace/project-c
  subpath:
    - .kiro/hooks
    - .vscode/settings.json

# Copy mode for tool compatibility
project-d:
  target: /Users/username/workspace/project-d
  subpath:
    - .kiro/hooks                    # symlink (default)
    - path: .kiro/steering/rules.md  # physical copy
      copy: true
```

### Strengths

- Focused on per-project development files
- Centralized configuration for all projects
- Automatic Git exclude management
- Supports both symlinks and physical copies
- Subpath selection for granular control
- Simple and lightweight
- No version control overhead
- Tested on macOS and Linux

### Limitations

- Not designed for `$HOME` dotfiles
- No templating features
- No encryption or secrets management
- No built-in remote sync (intentionally)
- Copy mode only supports single files, not directories
- Windows support implemented but not yet tested

### When to Use beyond-local-file

- Managing local development files across multiple projects
- Files that shouldn't be committed to Git (HTTP client configs, AI agent hooks, task runner configs)
- Need automatic Git exclude handling
- Tools that don't follow symlinks (copy mode)
- Different project layouts requiring flexible subpath selection

---

## Side-by-Side Comparison

| Aspect | GNU Stow | chezmoi | beyond-local-file |
|--------|----------|---------|-------------------|
| **Primary use case** | Dotfiles in `$HOME` | Dotfiles across machines | Per-project dev files |
| **Configuration** | CLI parameters + `.stowrc` | Source directory + templates | Centralized `config.yml` |
| **Target scope** | Single target directory | `$HOME` directory | Multiple projects simultaneously |
| **Version control** | Optional (manual Git) | Built-in Git workflow | Not included (intentionally) |
| **Templating** | None | Go templates for customization | None |
| **Secrets management** | Manual | Password managers + encryption | Not applicable |
| **Git integration** | Manual `.gitignore` | Manages dotfiles in Git | Auto Git exclude updates |
| **Link strategy** | Symlinks only | Copies files to target | Symlinks + physical copies |
| **Complexity** | Simple | Feature-rich | Minimal |
| **Learning curve** | Low | Medium-High | Low |
| **Cross-platform** | Unix-like (Linux, macOS) | Yes (Linux, macOS, Windows) | Implemented (macOS/Linux tested, Windows untested) |

---

## Use Case Examples

### Example 1: Personal Dotfiles

**Scenario:** You want to manage your `.bashrc`, `.vimrc`, and `.gitconfig` across your personal laptop and work machine.

**Best choice:** **chezmoi** (if you need machine-specific configs) or **GNU Stow** (if configs are identical)

**Why:**
- Designed for `$HOME` dotfiles
- chezmoi's templating handles work vs. personal email in `.gitconfig`
- Git-based sync keeps machines in sync
- Encryption for sensitive tokens

### Example 2: HTTP Client Files

**Scenario:** You have `.http` files with environment variables for testing APIs across 5 different projects. The files contain local URLs and test credentials that shouldn't be committed.

**Best choice:** **beyond-local-file**

**Why:**
- Per-project files, not `$HOME` dotfiles
- Automatic Git exclude handling
- Centralized management across all projects
- No version control overhead for local-only files

### Example 3: AI Agent Configuration

**Scenario:** You use Kiro AI assistant and want to share hooks and steering documents across multiple projects. Some tools don't follow symlinks.

**Best choice:** **beyond-local-file**

**Why:**
- Per-project configuration files
- Copy mode for tools that don't follow symlinks
- Subpath selection (only sync specific hooks)
- Automatic Git exclude updates

### Example 4: Development Container Dotfiles

**Scenario:** You frequently spin up development containers and want your shell configuration available immediately.

**Best choice:** **chezmoi**

**Why:**
- One-shot initialization: `chezmoi init --apply username`
- Designed for ephemeral environments
- Git-based, no local state needed

---

## Can They Work Together?

Yes! These tools serve different purposes and can complement each other:

- **Use chezmoi or Stow** for your personal dotfiles in `$HOME` (`.bashrc`, `.vimrc`, `.gitconfig`)
- **Use beyond-local-file** for per-project development files (HTTP client configs, AI hooks, task runner configs)

Example setup:

```
# chezmoi manages $HOME dotfiles
~/.bashrc -> managed by chezmoi
~/.vimrc -> managed by chezmoi
~/.gitconfig -> managed by chezmoi

# beyond-local-file manages per-project files
~/workspace/project-a/test.http -> managed by beyond-local-file
~/workspace/project-a/.kiro/hooks/ -> managed by beyond-local-file
~/workspace/project-b/dev-config.yml -> managed by beyond-local-file
```

---

## Migration Considerations

### From Stow to beyond-local-file

**When to migrate:** If you're using Stow for per-project files instead of `$HOME` dotfiles.

**Steps:**
1. Create a managed projects directory
2. Move project-specific files from Stow packages
3. Create `config.yml` mapping projects to targets
4. Run `blf link sync`
5. Keep Stow for `$HOME` dotfiles

### From chezmoi to beyond-local-file

**When to migrate:** If you're using chezmoi for per-project files and don't need templating/encryption.

**Steps:**
1. Extract per-project files from chezmoi source directory
2. Create managed projects directory structure
3. Create `config.yml` with project mappings
4. Run `blf link sync`
5. Keep chezmoi for `$HOME` dotfiles

### From Shell Scripts to beyond-local-file

**When to migrate:** If you have custom scripts for syncing files across projects.

**Benefits:**
- Built-in status checking and conflict detection
- Automatic Git exclude management
- Cross-platform support
- Copy mode for tool compatibility
- No need to maintain sync logic

---

## Conclusion

Choose the tool that matches your use case:

- **GNU Stow:** Simple dotfiles in `$HOME`
- **chezmoi:** Complex dotfiles across machines with templating/encryption
- **beyond-local-file:** Per-project development files with Git exclude automation

All three are excellent tools for their intended purposes. Understanding the differences helps you pick the right one — or use them together for a complete solution.
