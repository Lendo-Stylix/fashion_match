#!/usr/bin/env bash
# Package OutfitMatch frontend into a zip for download.
# Excludes: node_modules, .next, .git, dev/server logs, IDE caches,
#           Prisma DB, sandbox infra, examples.

set -euo pipefail

SRC="/home/z/my-project"
OUT="/home/z/my-project/download/outfitmatch-frontend.zip"
STAGE="/tmp/outfitmatch-frontend-stage"

# Clean stage
rm -rf "$STAGE" "$OUT"
mkdir -p "$STAGE/outfitmatch-frontend"

# Copy with excludes using rsync
rsync -a \
  --exclude='node_modules' \
  --exclude='.next' \
  --exclude='.git' \
  --exclude='.turbo' \
  --exclude='*.log' \
  --exclude='dev.log' \
  --exclude='server.log' \
  --exclude='.zscripts' \
  --exclude='dev.pid' \
  --exclude='tsconfig.tsbuildinfo' \
  --exclude='.eslintcache' \
  --exclude='.idea' \
  --exclude='.vscode' \
  --exclude='.DS_Store' \
  --exclude='db/*.db' \
  --exclude='db/*.db-journal' \
  --exclude='prisma/migrations/dev.db*' \
  --exclude='download' \
  --exclude='upload' \
  --exclude='examples' \
  --exclude='mini-services' \
  --exclude='skills' \
  --exclude='.cache' \
  --exclude='coverage' \
  --exclude='*.tsbuildinfo' \
  --exclude='worklog.md' \
  --exclude='Caddyfile' \
  --exclude='.zscripts' \
  "$SRC/" "$STAGE/outfitmatch-frontend/"

# Show what's included (sanity check)
echo "── Packaged contents (top-level):"
ls -la "$STAGE/outfitmatch-frontend/"
echo ""
echo "── Total size:"
du -sh "$STAGE/outfitmatch-frontend/"

# Create zip
cd "$STAGE"
zip -r -q "$OUT" "outfitmatch-frontend"

echo ""
echo "── Zip created:"
ls -la "$OUT"

# Cleanup stage
rm -rf "$STAGE"
