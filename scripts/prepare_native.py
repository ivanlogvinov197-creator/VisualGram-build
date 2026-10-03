"""Prepare the pinned official Telegram source for a standalone signed build."""
import argparse
import json
import os
from pathlib import Path
import re

UPSTREAM_REVISION = "6ad963e5b62d354da79040f388ae2b9132fb17b8"


def replace(path, old, new, expected=1):
    source = path.read_text(encoding="utf-8")
    if source.count(old) != expected:
        raise ValueError(f"Unsupported source layout: {path.name}")
    path.write_text(source.replace(old, new), encoding="utf-8", newline="\n")


def prepare(root):
    # A single ad-hoc profile cannot sign Telegram's separate extension targets.
    replace(root / "Telegram/BUILD",
            'name = "disableExtensions",\n    build_setting_default = False,',
            'name = "disableExtensions",\n    build_setting_default = True,')
    # Use the private app sandbox. Never borrow another app's provisioned group.
    replace(root / "Telegram/BUILD",
            '<string>group.{telegram_bundle_id}</string>',
            '', expected=1)
    delegate = root / "submodules/TelegramUI/Sources/AppDelegate.swift"
    replace(delegate, 'configuration.sharedContainerIdentifier = appGroupName',
            'configuration.sharedContainerIdentifier = nil')
    replace(delegate,
            '        let baseAppBundleId = Bundle.main.bundleIdentifier!\n        let appGroupName = "group.\\(baseAppBundleId)"\n\n        let configuration = URLSessionConfiguration.background',
            '        let configuration = URLSessionConfiguration.background')
    replace(delegate, '        let appGroupName = "group.\\(baseAppBundleId)"\n',
            '', expected=1)
    replace(delegate,
            'let maybeAppGroupUrl = FileManager.default.containerURL(forSecurityApplicationGroupIdentifier: appGroupName)',
            'let maybeAppGroupUrl = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first')
    replace(delegate, '        if !isUITest {\n            performAppGroupUpgrades',
            '        try? FileManager.default.createDirectory(atPath: rootPath, withIntermediateDirectories: true, attributes: nil)\n        if !isUITest {\n            performAppGroupUpgrades')
    replace(delegate, '            performAppGroupUpgrades(appGroupPath: appGroupUrl.path, rootPath: rootPath)',
            '            var backupUrl = URL(fileURLWithPath: rootPath)\n            var backupValues = URLResourceValues()\n            backupValues.isExcludedFromBackup = true\n            try? backupUrl.setResourceValues(backupValues)')
    # Bound concurrent compiler processes to standard hosted runner memory.
    with (root / ".bazelrc").open("a", encoding="utf-8", newline="\n") as output:
        output.write("\n# VisualGram hosted build\nbuild --jobs=2\n")


def configuration(output):
    api_id = os.environ["TELEGRAM_API_ID"]
    api_hash = os.environ["TELEGRAM_API_HASH"]
    if not api_id.isdigit() or not re.fullmatch(r"[a-fA-F0-9]{32}", api_hash):
        raise ValueError("Valid Telegram API credentials are required.")
    data = dict(bundle_id=os.environ["APP_BUNDLE_ID"], api_id=api_id,
                api_hash=api_hash, team_id=os.environ["SIGNING_TEAM"],
                app_center_id="0", is_internal_build="false",
                is_appstore_build="false", appstore_id="0",
                app_specific_url_scheme="visualgram", premium_iap_product_id="",
                enable_siri=False, enable_icloud=False)
    output.write_text(json.dumps(data), encoding="utf-8")
    output.chmod(0o600)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("--configuration", type=Path)
    args = parser.parse_args()
    prepare(args.source)
    if args.configuration:
        configuration(args.configuration)
    print("Native Telegram source prepared; credentials were not printed.")
