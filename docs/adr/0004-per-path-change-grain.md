# Per-path change grain under a directory item

A directory named as an item in a mapping is the watch root, not the queue unit. The daemon queues **create**, **update**, and **delete** of paths inside that item. Update catch-up then means “only these paths moved,” and stale-base conflict is per path.

Tree-as-one-hash was rejected: one file edited during downtime would be a directory-wide change, which makes “only detected changes” false and makes two independent file edits a single conflict. Per-file subpaths in `config.yml` were rejected: adding a hook would be a mapping edit.

Change types exist so later releases can attach triggers before or after apply; 0.5.0 ships the types, not the trigger hooks.

## Status

accepted
