#!/usr/bin/env bash
# Builds the DokuWiki aichat plugin with streamed answers and reasoning: downloads upstream at
# the pinned commit, applies streaming.patch and packs aichat-streaming.tar.gz next to this
# script, for Admin -> Extension Manager -> Manual Install -> upload. Runs on Linux and in
# Git Bash on Windows; needs curl, tar and git or patch.
#
# For a newer upstream version: set COMMIT, run this, fix any rejected hunks in a clone of
# upstream and export the patch again (README.md in this folder).
set -euo pipefail

UPSTREAM=https://github.com/cosmocode/dokuwiki-plugin-aichat
COMMIT=dd5f5042c47f7fd4f037c26d06acf3893d966753 # 2026-08-28, plugin date 2026-08-27

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

echo "downloading aichat at ${COMMIT:0:10}"
curl -fsSL "$UPSTREAM/archive/$COMMIT.tar.gz" | tar -xz -C "$WORK"
mv "$WORK/dokuwiki-plugin-aichat-$COMMIT" "$WORK/aichat"

echo "applying streaming.patch"
if command -v git >/dev/null; then
  (cd "$WORK/aichat" && git apply --whitespace=nowarn "$HERE/streaming.patch")
else
  patch -p1 -d "$WORK/aichat" < "$HERE/streaming.patch"
fi

tar -czf "$HERE/aichat-streaming.tar.gz" -C "$WORK" aichat
echo "built $HERE/aichat-streaming.tar.gz"
echo "install: Admin -> Extension Manager -> Manual Install -> upload this file (replaces an installed aichat)"
