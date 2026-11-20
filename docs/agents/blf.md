# Local files

beyond-local-file projects some files into this working tree. When this tree is a git repo, it lists those items in `.git/info/exclude`. The copy in this tree is the working copy. The durable copy is the hub file. This repo's git records the other files.

## Ask beyond-local-file

beyond-local-file is the only source for which paths are projected and where their hub files live. Do not read its mapping files or `.git/info/exclude` to work that out.

The program is `$BLF_CMD` when that variable is set, else `blf`. When the program is not found, or exits non-zero, ask the user for the command that runs beyond-local-file and use it for the rest of the session. When that fails too, report the error and stop. Do not guess a hub path.

Run `PROGRAM managed` in this working tree. It prints JSON. `PROGRAM managed --schema` describes every field.

The top-level `managed` flag answers a project-level question: does beyond-local-file project anything into this tree? It does not say whether one path is projected. Answer that from `managed_projects[].items`:

- A path is a projection when its path relative to `target` equals an item `path` or sits inside it. Take `target` from the answer: `is_target_root` false means this tree is below it.
- Every other path is a normal file in this repo.
- The hub file is the item's `hub_path`, plus the rest of the path when the item is a directory. It belongs to the managed project that lists the item.
- That project's `git` field says where the hub commit runs. `git.is_repo` true: in `git.root`, which can be above the managed project directory. `git.is_repo` false: the hub is not a git repo, there is nothing to commit there, and the working-tree copy is all that needs saving.

When `managed` is false, nothing here is projected. Stop.

## Commits

Suggesting a commit message includes two subjects: one for this repo, and one for the hub. List the hub paths beside the hub subject. Stop there. Neither repo is committed while implementing.

When the user asks to commit:

1. Commit this repo with the subject they asked for. When every change is a projection, this repo has nothing to commit. That empty step is success, and the request continues. When the commit fails, stop. The hub stays uncommitted.
2. Run `PROGRAM managed` and check each path this conversation created or edited against `managed_projects[].items`. The paths that sit inside an item are projections.
3. Resolve each projection's hub file. Stage it only when its bytes match the working-tree file. When the bytes differ, leave it unstaged and report the path.
4. For a managed project whose `git.is_repo` is false, say there is nothing to commit and do not stage or commit for it. Otherwise commit the staged hub paths in `git.root`. The subject is `{PREFIX}: {the subject they asked for}`. `PREFIX` is the text before the colon on the latest commit in that hub repo that touches the managed-project directory. When that subject has no colon, `PREFIX` is the managed project name.
5. Other dirty paths in the hub repo stay unstaged.
6. Push a repo when the user asks for a push.
