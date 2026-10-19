#!/usr/bin/env bash
# Veyra RC3 install from extracted ZIP copied into /home/jnsadmin/veyra-rc3
# Use: sudo bash <this-script> /home/jnsadmin/veyra-rc3
set -Eeuo pipefail
dir="${1:-/home/jnsadmin/veyra-rc3}"
if [ "$(id -u)" != 0 ]; then echo 'Run as root with sudo'; exit 2; fi
if [ ! -f "$dir/install.sh" ] || [ ! -f "$dir/manifest.json" ]; then
 echo "Release files missing from $dir. Unzip the RC3 package to this folder first."; exit 3
fi
cd "$dir"
bash -n install.sh
exec bash ./install.sh
