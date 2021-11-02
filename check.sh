#!/bin/bash
#

set -e

./scripts/sequence-patch.sh --fast
cd tmp/current/
./run_oldconfig.sh --check
