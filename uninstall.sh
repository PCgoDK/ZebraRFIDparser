#!/usr/bin/env bash
set -euo pipefail

APP_NAME="rfid-event-collector"
APP_DIR="/opt/${APP_NAME}"
CONFIG_DIR="/etc/${APP_NAME}"
DATA_DIR="/var/lib/${APP_NAME}"
SERVICE_NAME="rfid-receiver.service"
SERVICE_TARGET="/etc/systemd/system/${SERVICE_NAME}"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Please run as root (sudo)."
  exit 1
fi

if systemctl list-unit-files | grep -q "^${SERVICE_NAME}"; then
  systemctl disable --now "${SERVICE_NAME}" || true
fi

rm -f "${SERVICE_TARGET}"
systemctl daemon-reload

rm -rf "${APP_DIR}" "${CONFIG_DIR}" "${DATA_DIR}"

echo "Uninstalled ${APP_NAME}."
