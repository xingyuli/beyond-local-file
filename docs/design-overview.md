# Design Overview

High-level architecture. Mapping expansion is in [design-model-separation.md](design-model-separation.md). The daemon runtime is in [design-daemon.html](design-daemon.html). Domain language is in [CONTEXT.md](../CONTEXT.md).

## Copy-only projection

A **link** is always a physical copy at the projection path (ADR 0001). That path is not a symlink to the hub. Nested symlink nodes inside a directory item are copied as symlinks (ADR 0013). Leftover blf symlinks at a projection path become copies on daemon catch-up.

`copy_projection` writes one projection. Catch-up, live fan-out, and revlink all call it. Git exclude is `GitExcludeManager`. There is no link-strategy protocol and no second projection mechanism.

## Configuration to mapping units

YAML maps to `ConfigProject` / `Mapping` (user intent). Translation expands those into `MappingUnit` rows: one managed project × one target, with discovered items. See [design-model-separation.md](design-model-separation.md).

## Daemon

One OS process per configuration set writes hubs, fans out, and serves shells over localhost IPC. Live observe, catch-up, and mutating shells run per worker unit. See [design-daemon.html](design-daemon.html) and ADRs 0005, 0006, and 0021.

## Further reading

- [CONTEXT.md](../CONTEXT.md) — domain language
- [design-model-separation.md](design-model-separation.md) — config vs mapping-unit models
- [design-daemon.html](design-daemon.html) — daemon runtime
- [development.md](development.md) — contributing
- [configuration-reference.md](configuration-reference.md) — mapping yaml
