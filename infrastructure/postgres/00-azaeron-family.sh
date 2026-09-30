#!/bin/sh
set -eu
printf '%s\n' postgres16-alpine-v1 > "$PGDATA/.azaeron-runtime-family"
