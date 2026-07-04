#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STAMP="${SAFE_TRASH_STAMP:-$(date -u +%Y%m%dT%H%M%SZ)}"
DEST_ROOT="$ROOT/Trash/$STAMP"

usage() {
  echo "Usage: $0 [--stdin0] <project-relative-path>..." >&2
}

normalize_relative_path() {
  local raw="$1"
  local rel

  if [[ -z "$raw" ]]; then
    return 1
  fi

  case "$raw" in
    "$ROOT"/*)
      rel="${raw#"$ROOT"/}"
      ;;
    /*)
      echo "Refusing path outside project root: $raw" >&2
      return 2
      ;;
    *)
      rel="${raw#./}"
      ;;
  esac

  case "$rel" in
    ""|"."|".."|../*|*/../*|*/..)
      echo "Refusing unsafe path: $raw" >&2
      return 2
      ;;
  esac

  printf '%s\n' "$rel"
}

move_one() {
  local raw="$1"
  local rel
  rel="$(normalize_relative_path "$raw")"

  local src="$ROOT/$rel"
  if [[ ! -e "$src" ]]; then
    echo "Skipping missing path: $rel" >&2
    return 0
  fi

  local dest="$DEST_ROOT/$rel"
  mkdir -p "$(dirname "$dest")"

  if [[ -e "$dest" ]]; then
    local suffix=1
    while [[ -e "${dest}.${suffix}" ]]; do
      suffix=$((suffix + 1))
    done
    dest="${dest}.${suffix}"
  fi

  mv "$src" "$dest"
  echo "$rel -> ${dest#"$ROOT"/}"
}

if [[ "${1:-}" == "--stdin0" ]]; then
  while IFS= read -r -d '' path; do
    move_one "$path"
  done
  exit 0
fi

if [[ "$#" -eq 0 ]]; then
  usage
  exit 2
fi

for path in "$@"; do
  move_one "$path"
done
