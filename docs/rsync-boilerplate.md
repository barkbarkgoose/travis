*a reasonable and safe way to perform an initial boilerplate update:**

1. Commit the destination project.
2. Create a branch for the boilerplate update.
3. Clone or prepare the new boilerplate.
4. Run `rsync` with a dry run first.
5. Review the diff.
6. Run tests and manually verify the app.

Use exclusions for project state and secrets:

```bash
rsync -av \
  --exclude='.git/' \
  --exclude='backend/.env' \
  --exclude='backend/db.sqlite3' \
  --exclude='frontend/node_modules/' \
  --exclude='frontend/dist/' \
  --dry-run \
  /path/to/boilerplate/ \
  /path/to/project/
```

Then remove `--dry-run` once the file list looks correct.

For recurring updates, Git is usually better than rsync if the project shares the boilerplate’s history:

```bash
git remote add boilerplate /path/to/greenfield-boilerplate
git fetch boilerplate
git merge boilerplate/main
```

Git will identify conflicts in shared files such as `package.json`, router files, app shell components, auth code, and settings. Rsync cannot distinguish boilerplate-owned code from custom project code and may silently overwrite it.

A practical rule:

- Boilerplate-owned files: safe to synchronize
- App-specific directories and features: exclude
- Shared integration files: synchronize, then manually review
- Secrets, databases, dependencies, and build output: always exclude

So: **rsync is good for a controlled first update; Git remotes or a dedicated upstream-sync process are better long term.** Never use `--delete` until you have a very clear ownership map.

