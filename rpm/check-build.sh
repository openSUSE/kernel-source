#!/bin/bash
# Copyright (c) 2004 SuSE Linux AG, Germany.  All rights reserved.

if grep -q "Linux version 2\.[0-5]\." /proc/version; then
  echo "FATAL: kernel too old, need kernel >= 2.6 for this package"
  exit 1
fi

exit 0

