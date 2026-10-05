# Restore undoes create's fan-out

Create from a target copies into the hub and fans out to every other replica. Restore is that inverse: the requesting target's file stays as an unmanaged local file, the hub copy and the other replicas' projections are deleted, the subpath is dropped. Git exclude is removed on every replica that stops projecting the item, including the requesting target whose file remains.

## Status

accepted

## Considered Options

- Leave other targets' copies as unmanaged files (0006). Rejected: those copies exist because create (or catch-up) installed them; restore would not reverse create.
- Delete every copy including the requesting target. Rejected: that is remove.
