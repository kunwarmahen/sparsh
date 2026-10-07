#!/usr/bin/env bash
# Build and sign WebDriverAgent on a Mac, so Sparsh can drive an iPhone.
#
# Runs on the Mac -- at its keyboard, or over SSH from Linux:
#
#   scp scripts/build-wda-on-mac.sh mac.local:
#   ssh -t mac.local ./build-wda-on-mac.sh            # build WDA.ipa
#   ssh -t mac.local ./build-wda-on-mac.sh --run      # or: run it from the Mac
#
# What it needs, once, done in the Mac's own windows (Screen Sharing
# works for this):
#   * Xcode from the App Store, opened once to finish installing.
#   * An Apple ID added in Xcode > Settings > Accounts. A free one works;
#     what it signs stops opening after 7 days, and this is run again.
#   * The iPhone plugged into the Mac once, unlocked, "Trust This
#     Computer" answered -- so Xcode can add it to the signing profile.
#
# What it makes: ~/sparsh-wda/WDA.ipa, to copy to Linux and start there
# with scripts/start-wda-from-linux.sh. The Mac isn't needed after that
# until the signature runs out.
#
# Settings (environment):
#   TEAM     the Apple team id (10 letters and digits). Found from the
#            signing certificate when not given.
#   PREFIX   the start of WDA's bundle id; must be yours, not Facebook's
#            (default com.<mac user>.sparsh)
#   UDID     with --run: which iPhone (default: the only one plugged in)

set -euo pipefail

HERE="$HOME/sparsh-wda"
WDA="$HERE/WebDriverAgent"
PREFIX="${PREFIX:-com.$(id -un | tr -cd 'a-zA-Z0-9').sparsh}"
RUN=0
[ "${1:-}" = "--run" ] && RUN=1

say() { printf '\n== %s\n' "$*"; }
die() { printf 'build-wda: %s\n' "$*" >&2; exit 1; }

[ "$(uname)" = "Darwin" ] || die "this runs on the Mac, not here"
command -v xcodebuild >/dev/null || die "Xcode isn't installed (App Store, then open it once)"
xcodebuild -version >/dev/null 2>&1 \
  || die "Xcode isn't ready: open it once, or run: sudo xcode-select -s /Applications/Xcode.app"

if [ -z "${TEAM:-}" ]; then
  # The team id is the OU of the "Apple Development" certificate Xcode made.
  TEAM="$(security find-certificate -c "Apple Development" -p 2>/dev/null \
    | openssl x509 -noout -subject 2>/dev/null \
    | sed -n 's/.*OU *= *\([A-Z0-9]\{10\}\).*/\1/p' | head -1)"
fi
[ -n "${TEAM:-}" ] || die "no Apple team found. Add an Apple ID in Xcode > Settings > Accounts,
  press 'Manage Certificates' > + > Apple Development, then run this again (or set TEAM=...)"

if [ -n "${SSH_CONNECTION:-}" ]; then
  # Over SSH the login keychain is locked, and signing fails with
  # "errSecInternalComponent" unless it is opened first.
  say "unlocking the login keychain (the Mac user's password)"
  security unlock-keychain "$HOME/Library/Keychains/login.keychain-db"
fi

mkdir -p "$HERE"
if [ -d "$WDA/.git" ]; then
  say "updating WebDriverAgent"
  git -C "$WDA" checkout -q -- . && git -C "$WDA" pull -q --ff-only
else
  say "fetching WebDriverAgent"
  git clone -q --depth 1 https://github.com/appium/WebDriverAgent "$WDA"
fi

# The project ships with Facebook's bundle ids; Apple won't sign those
# for anyone else.
sed -i '' "s/com\.facebook\.WebDriverAgent/$PREFIX.WebDriverAgent/g" \
  "$WDA/WebDriverAgent.xcodeproj/project.pbxproj"

say "building for team $TEAM as $PREFIX.WebDriverAgentRunner (a few minutes the first time)"
xcodebuild build-for-testing \
  -project "$WDA/WebDriverAgent.xcodeproj" \
  -scheme WebDriverAgentRunner \
  -destination 'generic/platform=iOS' \
  -derivedDataPath "$HERE/build" \
  -allowProvisioningUpdates \
  DEVELOPMENT_TEAM="$TEAM" CODE_SIGN_STYLE=Automatic \
  | grep -E '^(\*\*|error|warning: .*sign)' || true

PRODUCTS="$HERE/build/Build/Products"
APP="$PRODUCTS/Debug-iphoneos/WebDriverAgentRunner-Runner.app"
[ -d "$APP" ] || die "the build didn't make $APP -- run it again without the grep to see why:
  xcodebuild build-for-testing -project $WDA/WebDriverAgent.xcodeproj -scheme WebDriverAgentRunner \\
    -destination generic/platform=iOS -allowProvisioningUpdates DEVELOPMENT_TEAM=$TEAM"

if [ "$RUN" = 1 ]; then
  if [ -z "${UDID:-}" ]; then
    UDID="$(xcrun xctrace list devices 2>/dev/null \
      | grep -v Simulator | sed -n 's/.*(\([0-9A-Fa-f-]\{24,\}\))$/\1/p' | head -1)"
  fi
  [ -n "${UDID:-}" ] || die "no iPhone plugged into this Mac (or set UDID=...)"
  XCTESTRUN="$(ls "$PRODUCTS"/*.xctestrun | head -1)"
  say "starting WDA on $UDID -- leave this running; Ctrl-C stops it"
  echo "From Linux: sparsh look --serial http://<the iPhone's Wi-Fi address>:8100"
  exec xcodebuild test-without-building -xctestrun "$XCTESTRUN" -destination "id=$UDID"
fi

say "packing WDA.ipa"
rm -rf "$HERE/Payload" "$HERE/WDA.ipa"
mkdir "$HERE/Payload"
cp -R "$APP" "$HERE/Payload/"
(cd "$HERE" && zip -qr WDA.ipa Payload && rm -rf Payload)
UNTIL="$(security cms -D -i "$APP/embedded.mobileprovision" 2>/dev/null \
  | plutil -extract ExpirationDate raw -o - - 2>/dev/null || echo "unknown")"

cat <<EOF

Built: $HERE/WDA.ipa  (bundle id $PREFIX.WebDriverAgentRunner.xctrunner)
Signed until: $UNTIL  -- run this again before then.

On Linux, with the iPhone plugged in there:
  scp $(id -un)@$(hostname):sparsh-wda/WDA.ipa .
  PREFIX=$PREFIX scripts/start-wda-from-linux.sh WDA.ipa
EOF
