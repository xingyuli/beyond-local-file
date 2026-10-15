# Out-of-sync replica on a lost update CAS

A target update is allowed only when its base generation/hash still matches the hub. Example: hub, app-a, and app-b at gen 1; both targets edit `foo`. The first observed update applies (hub gen 2) and fans out to in-sync replicas except the source. The second fails CAS and that replica is **out-of-sync** for `foo`: fan-out of `foo` skips it, and further path changes from it are discarded. The hub and in-sync replicas keep moving. The loser's bytes stay on disk.

This replaces freezing the whole path. Fan-out never writes the source replica. It also must not write a replica that has a pending mailbox entry for that path, or whose disk hash is not the expected base; that replica is marked out-of-sync instead of overwritten. A replica's later write stays an ordinary update while its base still matches the hub, including a file inside a directory it just created (0031). A direct edit on the managed project is a different writer: a replica that saves from the older generation is out-of-sync.

`daemon status` lists out-of-sync paths. `daemon start` does not ask a question: the resolve UI is served by the running daemon. `reload` warns; it does not block the daemon. Out-of-sync also clears when the replica's bytes later match the hub. A bare CLI is a poor place to pick winners; the resolve UI is 0024. Sequential merge is 0025; Submit is resolve.

## Status

accepted
