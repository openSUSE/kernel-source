#!/usr/bin/env bash
set -eu

# ──────────────────────────────────────────────
# fetch_todo_cves.sh — Fetch CVE related c-k-f output files from our remote worker.
#
# Requires rank_order_cves.py deployed on the source host.
#
# Fill in the CONFIG section below with your values before distributing.
#
# Run with one of:
#   -d, --dest <dir>    Download files to a local directory
#   --ls                  List matching files on source (dry run)
#
# Other:
#   -n <num>              Number of files to fetch (default: 10)
#   --reverse             Sort lowest priority first (delegate the boring ones)
#   --ai-rank             Use AI-based ranking logic
#   -h, --help            Show this message
# ──────────────────────────────────────────────

SRC_HOST="kss.prg2.suse.org"
SRC_USER="sles"
SCANNER_PATH="/home/$SRC_USER/scripts/rank_order_cves.py"

MODE=""            # "local" or "ls"
LOCAL_DIR=""
FILE_COUNT=10
REVERSE_FLAG=""
AI_RANK_FLAG=""

SSH_COMMON="-o StrictHostKeyChecking=accept-new -o ConnectTimeout=30"

src_ssh() { ssh $SSH_COMMON "${SRC_USER}@${SRC_HOST}" "$@"; }
src_scp() { scp $SSH_COMMON "$@"; }

die() { echo "ERROR: $*" >&2; exit 1; }

show_help() {
    cat << EOF
$(basename "$0") — Fetch top-priority security files from a remote server.

Requires rank_order_cves.py deployed on the source host.
Edit the CONFIG section at the top of the script to set the source host,
user, SSH key, and scanner path.

Usage:
  $(basename "$0") -d <dir> [options]
  $(basename "$0") --ls [options]

Modes:
  -d, --dest <dir>    Download files to a local directory
  --ls                  List matching files on source (dry run)

Options:
  -n <num>              Number of files to fetch (default: 10)
  --reverse             Sort lowest priority first (delegate the boring ones)
  --ai-rank             Use AI-based ranking logic
  -h, --help            Show this message

EOF
    exit 0
}

while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)      show_help ;;
        --ls)           MODE="ls"; shift ;;
        -d|--dest)   MODE="local"; LOCAL_DIR="$2"; shift 2 ;;
        -n)             FILE_COUNT="$2"; shift 2 ;;
        --reverse)      REVERSE_FLAG="--reverse"; shift ;;
        --ai-rank)      AI_RANK_FLAG="--ai-rank"; shift ;;
        *)
            echo "Unknown option: $1" >&2
            echo "Run '$(basename "$0") --help' for usage." >&2
            exit 1 ;;
    esac
done

[[ -n "$MODE" ]] || die "You must specify a mode: -d/--dest <dir> or --ls."

if [[ "$MODE" == "local" ]]; then
    [[ -n "$LOCAL_DIR" ]] || die "-d/--dest requires a directory argument."
    [[ -d "$LOCAL_DIR" ]] || die "Local directory does not exist: $LOCAL_DIR"
fi

if [[ "$MODE" == "ls" ]]; then
    src_ssh "python3 '${SCANNER_PATH}' -n '${FILE_COUNT}' --ls ${REVERSE_FLAG} ${AI_RANK_FLAG}"
    exit 0
fi

# ──────────────────────────────────────────────
# Transfer
# ──────────────────────────────────────────────
# 1. Isolate files on source to prevent races
echo "Scanning and isolating top ${FILE_COUNT} files on ${SRC_HOST}..."
REMOTE_OUTPUT=$(src_ssh "python3 '${SCANNER_PATH}' -n '${FILE_COUNT}' --isolate ${REVERSE_FLAG} ${AI_RANK_FLAG}")

ISOLATED_DIR=$(echo "$REMOTE_OUTPUT" | grep "^ISOLATED_DIR:" | cut -d':' -f2-)
[[ -n "$ISOLATED_DIR" ]] || die "Failed to get processing directory from source."
 
mapfile -t FILES < <(echo "$REMOTE_OUTPUT" | grep -v "^ISOLATED_DIR:" | grep -v "^SRC_DIR:")
 
if [[ ${#FILES[@]} -eq 0 ]]; then
    echo "No files matched the criteria."
    exit 0
fi
 
echo "Isolated ${#FILES[@]} file(s) in ${ISOLATED_DIR} on ${SRC_HOST}."
 
# 2. Download directly into the destination directory
echo "Downloading from ${SRC_HOST} to ${LOCAL_DIR}..."
if ! src_scp "${SRC_USER}@${SRC_HOST}:${ISOLATED_DIR}/*" "${LOCAL_DIR}/"; then
    echo "Download failed. Files remain isolated on source at: ${ISOLATED_DIR}" >&2
    exit 1
fi
 
echo "Copied ${#FILES[@]} file(s) to ${LOCAL_DIR}."
 
# 3. Summary — isolated dir is preserved on source
echo ""
echo "Isolated files preserved on ${SRC_HOST} at: ${ISOLATED_DIR}"
echo "Done. ${#FILES[@]} file(s) transferred: ${SRC_HOST} -> ${LOCAL_DIR}"