# No overlapping item paths on one target

Several managed projects may contribute items to one target project. Their item names must not be equal and must not nest (one a path prefix of the other). The same rule applies to two subpaths of one managed project. Start and reload fail after item discovery, naming both projects and both paths.

Last-writer-wins overlay (``local-file`` plus ``local-file/devops/k8s.md``) made whole-item hashes unmatchable and pinned live observe to the first hub. Tracking nested contribution source was rejected: flatten owned files into the directory item, or use disjoint items.

## Status

accepted

## Considered Options

- Allow overlay and record which managed project owns each nested path. Rejected: duplicates the mapping, and a directory item hash can never match a tree with foreign files.
- Warn and continue. Rejected: the daemon would still start in a state check cannot hash.
- Hard error after item discovery, including sync-all names. Accepted.
