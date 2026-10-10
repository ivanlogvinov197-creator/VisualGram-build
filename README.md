# Telegram with local visual profiles

Build patches for official Telegram-iOS revision `6ad963e5b62d354da79040f388ae2b9132fb17b8`.
These patches provide local gifts, scheduled gift delivery, profile appearance,
chat badges and shared appearance across accounts on the same device.
They do not change server ownership, payments, verification or subscriptions.
The display name is Telegram. Tap Chats three times within one second between
taps to open VisualGram. Appearance controls are hidden from Settings and profiles.
Local Stars history records purchases, sales, balance adjustments and the
25-Star NFT transfer fee; real payments and server transaction history are unchanged.

This repository contains only source patches and a manually triggered build workflow.
It does not contain signing assets, API credentials, user profiles or private history.
Required Actions Secrets: BUILD_CERTIFICATE_BASE64, BUILD_PROVISION_PROFILE_BASE64,
P12_PASSWORD, TELEGRAM_API_ID, TELEGRAM_API_HASH and IPA_EXPORT_PASSWORD.
IPA_EXPORT_PASSWORD must be an independently generated random value of at least 32 characters.

The workflow validates and signs the IPA, then encrypts it with OpenSSL
AES-256-CBC and PBKDF2-SHA256 (200000 iterations) before upload. Only the
encrypted file is uploaded, with one-day retention. Keep the export key private.
The final decrypted IPA is installed on the device covered by the provisioning profile.

The pinned upstream project and submodules retain their original licenses.
Full native compilation and device testing are required to confirm functionality.
