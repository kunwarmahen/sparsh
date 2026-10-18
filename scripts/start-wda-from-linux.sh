#!/usr/bin/env bash
# Install and start WebDriverAgent on an iPhone plugged into Linux.
#
#   scripts/start-wda-from-linux.sh WDA.ipa      # just built: install it first
#   scripts/start-wda-from-linux.sh              # already installed
#
# This is `sparsh iphone` now (src/sparsh/wdastart.py), kept so the steps
# written down elsewhere still work. That one command starts the iOS 17
# tunnel (no sudo), mounts the developer image the phone's iOS needs,
# finds WDA on the phone, forwards port 8100 and starts WDA, and starts
# it all again when the phone is plugged back in. PREFIX is no longer
# needed (WDA is found on the phone); when given, it is used.
#
# WDA.ipa comes from scripts/build-wda-on-mac.sh. go-ios is the `ios`
# program: `npm install -g --prefix ~/.local go-ios`. Linux also needs
# usbmuxd (`sudo apt install usbmuxd`) to see the phone at all.

set -euo pipefail

SPARSH="$(dirname "$0")/../.venv/bin/sparsh"
[ -x "$SPARSH" ] || SPARSH="$(command -v sparsh || true)"
[ -n "$SPARSH" ] || { echo "start-wda: sparsh isn't installed (uv sync, in this folder)" >&2; exit 1; }

exec "$SPARSH" iphone ${PREFIX:+--prefix "$PREFIX"} ${1:+"$(realpath "$1")"}
