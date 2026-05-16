# Shell Completion

`beyond-local-file` supports tab completion for `PROJECT_NAME` arguments in `link sync` and `link check`. Completions are read dynamically from the active config file, respecting `--config` and `~/.blfrc`.

## Before You Start: the `blf` Alias

The README recommends creating a `blf` alias for the long command name. Shell completion is registered for `beyond-local-file` by default — it does **not** automatically apply to aliases.

If you use `blf`, you need one extra step after the shell-specific setup below. The instructions for each shell include this step.

## Setup

### zsh

Add to `~/.zshrc`:

```zsh
autoload -Uz compinit && compinit
eval "$(_BEYOND_LOCAL_FILE_COMPLETE=zsh_source beyond-local-file)"
compdef _beyond_local_file_completion blf
```

> **Multi-user macOS** — if Homebrew was installed by a different account, you may see
> `compinit: insecure directories` warnings. Replace `compinit` with `compinit -u`:
>
> ```zsh
> autoload -Uz compinit && compinit -u
> eval "$(_BEYOND_LOCAL_FILE_COMPLETE=zsh_source beyond-local-file)"
> compdef _beyond_local_file_completion blf
> ```

### bash

Add to `~/.bashrc`:

```bash
eval "$(_BEYOND_LOCAL_FILE_COMPLETE=bash_source beyond-local-file)"
complete -F _beyond_local_file_completion blf
```

### fish

Add to `~/.config/fish/config.fish`:

```fish
_BEYOND_LOCAL_FILE_COMPLETE=fish_source beyond-local-file | source
```

Fish resolves aliases transparently, so no extra step is needed.

## Usage

Open a new terminal after setup, then press `<TAB>` after a command that accepts `PROJECT_NAME`:

```bash
blf link sync <TAB>       # shows: project-a  project-b  project-c
blf link check pro<TAB>   # narrows to names starting with "pro"
```

Completions come from whichever config is active — the `--config` flag, `~/.blfrc`, or the default `config.yml` in the current directory.

## See Also

- **[CLI Reference](cli-reference.md)** — Complete command documentation
- **[Config File Resolution](cli-reference.md#config-file-resolution-order)** — How the active config is determined
