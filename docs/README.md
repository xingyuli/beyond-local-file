# Documentation

Welcome to the beyond-local-file documentation!

## Getting Started

New to beyond-local-file? Start here:

1. **[Main README](../README.md)** - Overview, installation, and quick start
2. **[Alternatives Comparison](alternatives-comparison.md)** - How beyond-local-file compares to GNU Stow and chezmoi
3. **[Configuration Reference](configuration-reference.md)** - Complete configuration documentation
4. **[CLI Reference](cli-reference.md)** - Complete command-line interface documentation

## User Guides

### Core Documentation

- **[Alternatives Comparison](alternatives-comparison.md)** - Detailed comparison with GNU Stow and chezmoi
- **[Configuration Reference](configuration-reference.md)** - Complete configuration documentation
- **[CLI Reference](cli-reference.md)** - Complete command-line interface documentation
- **[Shell Completion](shell-completion.md)** - Tab completion setup for bash, zsh, and fish
- **[Config Format Clarification](config-format-clarification.md)** - Understanding configuration vs architecture
- **[Design Overview](design-overview.md)** - Architecture overview and design principles
- **[Daemon design](design-daemon.html)** - High-level daemon runtime (flowcharts)

### Design Documentation

- **[Daemon design](design-daemon.html)** - Process, live path, mappings, and resolve UI
- **[Design: Model Separation](design-model-separation.md)** - Two-model architecture (config vs processing)
- **[Design: Divide-and-Conquer](design-divide-and-conquer.md)** - Strategy management and protocol-based design

### Platform-Specific Guides

- **[Platform Support](platform-support.md)** - Cross-platform compatibility overview
- **[Windows Support](windows-support.md)** - Detailed Windows setup and troubleshooting

## Developer Documentation

- **[Development Guide](development.md)** - Contributing, testing, and development setup

## Quick Navigation

### I want to...

- **Get started quickly** → [Quick Start](../README.md#quick-start)
- **Set up tab completion** → [Shell Completion](shell-completion.md)
- **Compare with alternatives** → [Alternatives Comparison](alternatives-comparison.md)
- **Understand configuration** → [Configuration Reference](configuration-reference.md)
- **Learn all commands** → [CLI Reference](cli-reference.md)
- **Use on Windows** → [Windows Support](windows-support.md)
- **Understand the daemon** → [Daemon design](design-daemon.html)
- **Understand the architecture** → [Design Overview](design-overview.md)
- **Contribute code** → [Development Guide](development.md)

### Common Tasks

| Task | Documentation |
|------|---------------|
| Install the tool | [Installation](../README.md#installation) |
| Create first config | [Quick Start](../README.md#quick-start) |
| Project specific files only | [Configuration Reference](configuration-reference.md#subpath-mapping) |
| Start the daemon | [CLI Reference](cli-reference.md#daemon-start--start-the-runtime) |
| Check link status | [CLI Reference](cli-reference.md#link-check--verify-status) |
| Set up tab completion | [Shell Completion](shell-completion.md) |
| Use on Windows | [Windows Support](windows-support.md) |
| Run tests | [Development Guide](development.md#running-tests) |

## Documentation Structure

```
docs/
├── README.md                          # This file - documentation hub
│
├── User Guides
│   ├── alternatives-comparison.md     # Comparison with GNU Stow and chezmoi
│   ├── configuration-reference.md     # Complete configuration documentation
│   ├── cli-reference.md               # Complete CLI documentation
│   ├── shell-completion.md            # Tab completion setup
│   ├── config-format-clarification.md # Config vs architecture concepts
│   ├── platform-support.md            # Cross-platform guide
│   └── windows-support.md             # Windows-specific guide
│
├── Architecture
│   ├── architecture-design.md         # Detailed architecture
│   └── architecture-quick-reference.md # Quick overview
│
└── Development
    └── development.md                 # Contributing guide
```

## Need Help?

1. **Check the docs** - Most questions are answered here
2. **Search issues** - [Existing issues](https://github.com/xingyuli/beyond-local-file/issues)
3. **Ask questions** - [Open a new issue](https://github.com/xingyuli/beyond-local-file/issues/new)

## Contributing to Documentation

Documentation improvements are welcome! When contributing:

- Keep language clear and concise
- Include practical code examples
- Test all commands before documenting
- Update this index when adding new docs
- Follow the existing style and structure

See [Development Guide](development.md) for contribution guidelines.
