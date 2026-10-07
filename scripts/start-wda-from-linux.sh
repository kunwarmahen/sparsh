#!/usr/bin/env bash
# Install and start WebDriverAgent on an iPhone plugged into Linux.
#
#   PREFIX=com.someone.sparsh scripts/start-wda-from-linux.sh WDA.ipa
#   PREFIX=com.someone.sparsh scripts/start-wda-from-linux.sh      # already installed
#
# WDA.ipa comes from scripts/build-wda-on-mac.sh, with the same PREFIX.
# Sparsh reads when its signature runs out (`sparsh wda`), and says so in
# `sparsh devices` and `sparsh status` when two days or fewer are left.
# This uses go-ios (https://github.com/danielpaulus/go-ios), one program
# that speaks to an iPhone over USB from Linux: `npm install -g go-ios`,
# or a release binary called `ios` on PATH. Linux also needs usbmuxd
# (`sudo apt install usbmuxd`), which lets it see the phone at all.
#
# It leaves WDA running in the foreground (Ctrl-C stops it) and
# forwards port 8100, so on this machine:
#
#   sparsh look --serial http://127.0.0.1:8100
#
# Over Wi-Fi from any machine, the phone's own address works as well.

set -euo pipefail

IPA="${1:-}"
PREFIX="${PREFIX:?set PREFIX to what build-wda-on-mac.sh printed (com.<user>.sparsh)}"
BUNDLE="$PREFIX.WebDriverAgentRunner.xctrunner"

say() { printf '\n== %s\n' "$*"; }
die() { printf 'start-wda: %s\n' "$*" >&2; exit 1; }

command -v ios >/dev/null || die "go-ios isn't installed: npm install -g go-ios"

# Sparsh remembers when WDA's signature runs out, and refuses a run-out one
# here rather than letting the phone refuse it in Apple's words.
SPARSH="$(dirname "$0")/../.venv/bin/sparsh"
[ -x "$SPARSH" ] || SPARSH="$(command -v sparsh || true)"
if [ -n "$SPARSH" ]; then
  if [ -n "$IPA" ]; then "$SPARSH" wda "$IPA" || exit 1
  else "$SPARSH" wda || exit 1
  fi
fi
ios list | grep -q '[0-9a-fA-F]' || die "no iPhone found. Plug it in, unlock it, answer 'Trust',
  and check usbmuxd is running (sudo systemctl start usbmuxd)"

MAJOR="$(ios info 2>/dev/null | sed -n 's/.*"ProductVersion":"\([0-9]*\).*/\1/p')"
if [ "${MAJOR:-0}" -ge 17 ] && ! pgrep -f '[i]os tunnel start' >/dev/null; then
  # iOS 17 and later talk to developer tools through a tunnel, which
  # needs root to set up. It stays running in the background.
  say "iOS $MAJOR: starting the developer tunnel (asks for sudo)"
  sudo -b "$(command -v ios)" tunnel start >/tmp/sparsh-ios-tunnel.log 2>&1
  sleep 3
fi

if [ -n "$IPA" ]; then
  say "installing $IPA"
  ios install --path="$IPA"
  echo "First time only: on the iPhone, Settings > General > VPN & Device Management >"
  echo "trust the developer; and Settings > Privacy & Security > Developer Mode > on."
fi

say "forwarding port 8100"
ios forward 8100 8100 >/tmp/sparsh-ios-forward.log 2>&1 &
FORWARD=$!
trap 'kill $FORWARD 2>/dev/null || true' EXIT

say "starting WebDriverAgent ($BUNDLE) -- leave this running; Ctrl-C stops it"
echo "In another terminal: sparsh look --serial http://127.0.0.1:8100"
ios runwda --bundleid="$BUNDLE" --testrunnerbundleid="$BUNDLE" \
  --xctestconfig=WebDriverAgentRunner.xctest
