# Bugfix Requirements Document

## Introduction

`blf revlink create` and `blf revlink restore` silently skip the `.git/info/exclude` step
when the target path is nested (e.g. `docs/agent`). Only top-level paths (e.g. `myfile.txt`)
currently get the exclude entry written or removed.

The root cause is that all three affected methods instantiate `GitExcludeManager` with
`self.source.parent`. For a top-level path, `source.parent` is the project root where `.git`
lives, so `is_git_repo()` returns `True`. For a nested path, `source.parent` is an intermediate
directory with no `.git`, so `is_git_repo()` returns `False` and the step is silently skipped.

The fix must use `self.context.cwd` — the project root — as the `GitExcludeManager` target in
all three locations: `CreateOperation._git_exclude`, `CreateOperation._git_exclude_preview`, and
`RestoreOperation._git_exclude`.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN `blf revlink create` is run on a nested path (e.g. `docs/agent`) inside a selective-sync
mapping THEN the system silently skips writing the entry to `.git/info/exclude`

1.2 WHEN `blf revlink create --dry-run` is run on a nested path THEN the system omits the git
exclude action from the preview output, misleading the user into thinking no exclude entry will
be written

1.3 WHEN `blf revlink restore` is run on a nested path whose entry was previously added to
`.git/info/exclude` THEN the system silently skips removing the entry from `.git/info/exclude`

### Expected Behavior (Correct)

2.1 WHEN `blf revlink create` is run on a nested path inside a selective-sync mapping THEN the
system SHALL write the full relative path (e.g. `docs/agent`) to `.git/info/exclude` and report
the action to the user

2.2 WHEN `blf revlink create --dry-run` is run on a nested path THEN the system SHALL include the
git exclude action in the dry-run preview output

2.3 WHEN `blf revlink restore` is run on a nested path THEN the system SHALL remove the full
relative path from `.git/info/exclude` and report the action to the user

### Unchanged Behavior (Regression Prevention)

3.1 WHEN `blf revlink create` is run on a top-level path (e.g. `myfile.txt`) THEN the system
SHALL CONTINUE TO write the path name to `.git/info/exclude` exactly as before

3.2 WHEN `blf revlink create --dry-run` is run on a top-level path THEN the system SHALL
CONTINUE TO include the git exclude action in the preview output exactly as before

3.3 WHEN `blf revlink restore` is run on a top-level path THEN the system SHALL CONTINUE TO
remove the path name from `.git/info/exclude` exactly as before

3.4 WHEN `blf revlink create` or `blf revlink restore` is run and `self.context is None` (the
test-only escape hatch) THEN the system SHALL CONTINUE TO silently skip the git exclude step
without error
