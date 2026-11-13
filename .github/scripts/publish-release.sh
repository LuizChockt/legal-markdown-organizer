#!/usr/bin/env bash
# Called only after the exact main-branch commit passes the complete test matrix.
set -euo pipefail

# gh may print an error JSON body to stdout on HTTP 404, even with --jq.
# The command's exit status, not nonempty stdout, establishes whether a tag exists.
if existing="$(gh api "repos/$GH_REPO/git/ref/tags/v0.2.0" --jq '.object.sha' 2>/dev/null)"; then
  if [ "$existing" != "$RELEASE_SHA" ]; then
    echo "Existing v0.2.0 tag points to another object; refusing to change it." >&2
    exit 1
  fi
else
  # A concurrent creation or permission failure is rejected by GitHub; no force
  # update, replacement or deletion of an existing tag is ever attempted.
  gh api --method POST "repos/$GH_REPO/git/refs" -f ref=refs/tags/v0.2.0 -f sha="$RELEASE_SHA"
fi

gh release create v0.2.0 dist/* --verify-tag --title "Legal Markdown Organizer 0.2.0" --notes-file docs/releases/v0.2.0.md
