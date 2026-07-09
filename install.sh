#!/usr/bin/env bash
set -euo pipefail

APP_NAME="zebra-rfid-parser"
APP_DIR="/opt/${APP_NAME}"
CONFIG_DIR="/etc/${APP_NAME}"
DATA_DIR="/var/lib/${APP_NAME}"
SERVICE_NAME="zebra-rfid-parser.service"
SERVICE_TARGET="/etc/systemd/system/${SERVICE_NAME}"
USER_NAME="rfidcollector"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Please run as root (sudo)."
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required but not installed."
  exit 1
fi

if ! id -u "${USER_NAME}" >/dev/null 2>&1; then
  useradd --system --no-create-home --shell /usr/sbin/nologin "${USER_NAME}"
fi

mkdir -p "${APP_DIR}" "${CONFIG_DIR}" "${DATA_DIR}"

cp -r src sql "${APP_DIR}/"
cp systemd/${SERVICE_NAME} "${SERVICE_TARGET}"

python3 -m venv "${APP_DIR}/venv"
"${APP_DIR}/venv/bin/python" -m pip install --upgrade pip >/dev/null

if [[ ! -f "${CONFIG_DIR}/config.json" ]]; then
  cp config/config.json.example "${CONFIG_DIR}/config.json"
fi

chown -R "${USER_NAME}:${USER_NAME}" "${APP_DIR}" "${DATA_DIR}"
chmod 750 "${APP_DIR}" "${DATA_DIR}"
chmod 640 "${CONFIG_DIR}/config.json"

systemctl daemon-reload
systemctl enable --now "${SERVICE_NAME}"

echo "Installed ${APP_NAME}."
echo "Service status: systemctl status ${SERVICE_NAME}"
