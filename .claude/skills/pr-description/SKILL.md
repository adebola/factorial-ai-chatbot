---
name: pr-description
description: Writes pull request descriptions. Use when creating a PR or when the user asks to summarize changes for a pull request.
---

When writing a PR description:

1. Run `git diff origin..HEAD` to see all changes on this branch
2. Write a description following this format

## What
One sentence explaining what the PR does

## Why
Brief context on why this change is needed

## Changes

- Bullet points of specific changes
- Group related changes together
- Mention any files deleted or renamed

## Testing
How to verify this works. Included specific commands if relevant

Keep descriptions concise. focus on what a reviewer needs to know.
