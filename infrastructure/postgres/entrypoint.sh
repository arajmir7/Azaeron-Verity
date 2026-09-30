#!/bin/sh
set -eu
if [ "$(id -u)" = 0 ]; then
    echo "Azaeron PostgreSQL must run as the postgres user." >&2
    exit 1
fi
if [ "${1:-}" = postgres ]; then
    if [ -f "$PGDATA/PG_VERSION" ]; then
        if [ "$(cat "$PGDATA/.azaeron-runtime-family" 2>/dev/null || true)" != "postgres16-alpine-v1" ]; then
            echo "Unrecognized PGDATA family. Restore a logical dump into a NEW volume." >&2
            exit 1
        fi
    else
        case "${AZAERON_DATABASE_BOOTSTRAP:-}" in
            new-install|logical-restore) ;;
            *) echo "Explicit new-install or logical-restore bootstrap is required." >&2; exit 1 ;;
        esac
    fi
fi
exec /usr/local/bin/docker-entrypoint.sh "$@"
