#!/bin/bash
set -euo pipefail

TARGET_UID="${SHANNON_HOST_UID:-}"
TARGET_GID="${SHANNON_HOST_GID:-}"
CURRENT_UID=$(id -u pentest 2>/dev/null || echo "")

if [ -n "$TARGET_UID" ] && [ "$TARGET_UID" != "$CURRENT_UID" ] && [ "$TARGET_UID" != "0" ]; then
  userdel pentest 2>/dev/null || true
  groupdel pentest 2>/dev/null || true

  groupadd -g "$TARGET_GID" pentest 2>/dev/null || true
  useradd -u "$TARGET_UID" -g pentest -s /bin/bash -M pentest 2>/dev/null || true

  chown -R pentest:pentest /app/sessions /app/workspaces /tmp/.claude
fi

exec su -m pentest -c "exec $*"
