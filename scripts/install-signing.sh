#!/bin/bash
set -euo pipefail
umask 077

if [[ -z "${BUILD_CERTIFICATE_BASE64:-}" || -z "${BUILD_PROVISION_PROFILE_BASE64:-}" ]]; then
  echo '::error::Add BUILD_CERTIFICATE_BASE64 and BUILD_PROVISION_PROFILE_BASE64 to repository Actions Secrets.'
  exit 1
fi

printf '%s' "$BUILD_CERTIFICATE_BASE64" | base64 --decode > "$RUNNER_TEMP/signing.p12"
printf '%s' "$BUILD_PROVISION_PROFILE_BASE64" | base64 --decode > "$RUNNER_TEMP/profile.mobileprovision"
security cms -D -i "$RUNNER_TEMP/profile.mobileprovision" > "$RUNNER_TEMP/profile.plist"

# Apple Keychain may reject modern PKCS12 encryption. Re-encode the same key and
# certificate for import, retaining the original password. Never print key data.
task_openssl="$(brew --prefix openssl@3)/bin/openssl"
if ! "$task_openssl" pkcs12 -in "$RUNNER_TEMP/signing.p12" -passin env:P12_PASSWORD \
  -out "$RUNNER_TEMP/signing-key.pem" -noenc 2>/dev/null; then
  "$task_openssl" pkcs12 -legacy -in "$RUNNER_TEMP/signing.p12" -passin env:P12_PASSWORD \
    -out "$RUNNER_TEMP/signing-key.pem" -noenc
fi
"$task_openssl" pkcs12 -export -legacy -in "$RUNNER_TEMP/signing-key.pem" \
  -out "$RUNNER_TEMP/signing-compatible.p12" -passout env:P12_PASSWORD \
  -certpbe PBE-SHA1-3DES -keypbe PBE-SHA1-3DES -macalg sha1

task_keychain="$RUNNER_TEMP/visualgram-signing.keychain-db"
task_password="$(openssl rand -hex 32)"
echo "::add-mask::$task_password"
security create-keychain -p "$task_password" "$task_keychain"
security set-keychain-settings -lut 21600 "$task_keychain"
security unlock-keychain -p "$task_password" "$task_keychain"
security import "$RUNNER_TEMP/signing-compatible.p12" -P "$P12_PASSWORD" -A -t cert -f pkcs12 -k "$task_keychain"
rm -f "$RUNNER_TEMP/signing-key.pem" "$RUNNER_TEMP/signing-compatible.p12"
security set-key-partition-list -S apple-tool:,apple:,codesign: -k "$task_password" "$task_keychain" >/dev/null
security list-keychains -d user -s "$task_keychain"

python3 scripts/signing_metadata.py
mkdir -p "$HOME/Library/MobileDevice/Provisioning Profiles"
cp "$RUNNER_TEMP/profile.mobileprovision" "$HOME/Library/MobileDevice/Provisioning Profiles/visualgram-ci.mobileprovision"
