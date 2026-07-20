#!/usr/bin/env bash
# Fail if any tracked text file contains a CRLF line ending.
# Mirrors awesome-copilot's check-line-endings gate; pairs with .gitattributes.
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

# git grep -I skips binary files; -l lists matching files; $'\r' matches CR.
if matches=$(git grep -I --files-with-matches --perl-regexp '\r$' -- . 2>/dev/null); then
  echo "ERROR: CRLF line endings found in:" >&2
  echo "$matches" >&2
  exit 1
fi

echo "All tracked text files use LF line endings."
