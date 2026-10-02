# Using the Boilerplate as an Upstream Remote

This guide explains how to start a new application from this repository while
keeping the application in its own Git repository. The application can then
pull intentional updates from the boilerplate without sending application-
specific work back to it.

## Recommended Setup for a New Project

Clone the boilerplate first so its commit history is retained:

```bash
git clone <boilerplate-repository-url> my-project
cd my-project
```

Rename the cloned remote and add the new application's repository as `origin`:

```bash
git remote rename origin boilerplate
```

The resulting arrangement is:

```text
origin/main       Your application repository
boilerplate/main  The canonical boilerplate repository
main              Your local application branch, tracking origin/main
```

The application is still its own project. Retaining the boilerplate commits
only gives Git a common ancestor, which makes future updates easier to merge.

Confirm the remote and tracking setup with:

```bash
git remote -v
```

## Updating a Project

Create a branch before bringing in boilerplate changes:

```bash
git switch -c chore/update-boilerplate
```

Review the incoming commits, then merge them:

```bash
```

Git will usually merge changes automatically when the application did not
modify the same parts of a file. If both repositories changed the same file
or lines, resolve the conflict in the application branch, then run the full
test suite before merging the update branch into `main`.

Useful comparisons before merging include:

```bash
# Boilerplate commits not yet present in the application
git log --oneline main..boilerplate/main

# Application commits that are not part of the boilerplate
git log --oneline boilerplate/main..main

# Files changed by boilerplate since the branches diverged
git diff --stat main...boilerplate/main
```

## What Stays Project-Specific

Application-specific pages, models, integrations, and feature work remain in
the application's repository. They are not sent to `boilerplate` unless you
deliberately contribute a generalized improvement back to that repository.

Keep the application branch tracking `origin/main`, not
`boilerplate/main`. Fetching from `boilerplate` does not change files or make
the application branch track it.

Do not push application work to the boilerplate remote by accident:

```bash
git push origin main       # normal application work
git push boilerplate main  # only when intentionally contributing upstream
```

## Projects Created by Copying or a Repository Template

Some project-generation methods copy the boilerplate files without retaining
the boilerplate commit history. In that case, adding a remote is still useful
for inspection:

```bash
git remote add boilerplate <boilerplate-repository-url>
```

However, the project and boilerplate have unrelated histories, so a normal
merge will not have a meaningful common baseline. For those projects, use a
careful file migration instead:

1. Commit the application and create an update branch.
2. Run `rsync --dry-run` first.
3. Exclude `.git`, environment files, databases, dependencies, build output,
   and application-specific directories.
4. Apply the boilerplate changes.
5. Review `git status` and `git diff` for overwritten application work.
6. Run tests and commit the migration.

Do not use `git merge --allow-unrelated-histories` as a general update strategy.
It can be useful for a one-time history reconciliation, but it often creates
many conflicts because Git cannot tell which same-named files originated from
the boilerplate.

## Practical Ownership Rule

Treat boilerplate updates as intentional migrations, not automatic syncing.

- Shared foundation files may require manual conflict resolution.
- New application files should remain application-owned.
- Secrets, local databases, dependencies, and build artifacts should never be
  synchronized from the boilerplate.
- A boilerplate update should always happen on a reviewable branch.
