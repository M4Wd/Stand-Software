#!/usr/bin/env bash
# One-time setup on a Raspberry Pi (Raspberry Pi OS Bookworm or later).
# Run from the repo root: bash scripts/install.sh
set -euo pipefail

echo "== Enabling I2C and SPI =="
sudo raspi-config nonint do_i2c 0
sudo raspi-config nonint do_spi 0

echo "== Installing system packages =="
sudo apt-get update
sudo apt-get install -y python3-venv python3-pip pigpio i2c-tools

echo "== Starting pigpiod (drives the ESC PWM signal) =="
sudo systemctl enable pigpiod
sudo systemctl start pigpiod

echo "== Creating Python virtualenv =="
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo "== Installing systemd service =="
sudo cp scripts/drone-stand.service /etc/systemd/system/drone-stand.service
sudo systemctl daemon-reload
sudo systemctl enable drone-stand
sudo systemctl restart drone-stand

echo
echo "Done. Set mode: hardware in config.yaml once wiring is connected, then:"
echo "  sudo systemctl restart drone-stand"
echo "Dashboard: http://<pi-ip-address>:8000"
