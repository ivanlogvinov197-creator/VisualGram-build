"""Validate CI profile against installed identities, without printing profile data."""
import datetime
import hashlib
import os
from pathlib import Path
import plistlib
import re
import subprocess


def metadata(profile, identities, now=None):
    now = now or datetime.datetime.now(datetime.timezone.utc)
    expiration = profile["ExpirationDate"].replace(tzinfo=datetime.timezone.utc)
    if expiration <= now:
        raise ValueError("Provisioning profile expired; obtain a current profile.")
    if "iOS" not in profile.get("Platform", []):
        raise ValueError("An iOS provisioning profile is required.")
    entitlements = profile["Entitlements"]
    team = profile["TeamIdentifier"][0]
    application_id = entitlements["application-identifier"]
    prefix, bundle = application_id.split(".", 1)
    if prefix not in profile.get("ApplicationIdentifierPrefix", []):
        raise ValueError("Profile application identifier prefix does not match.")
    if "*" in bundle:
        bundle = bundle.replace("*", "visualgram.app")
    if not re.fullmatch(r"[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+", bundle):
        raise ValueError("Profile has an unsupported bundle identifier.")
    identity = next((hashlib.sha1(cert).hexdigest().upper()
                     for cert in profile["DeveloperCertificates"]
                     if hashlib.sha1(cert).hexdigest().upper() in identities), None)
    if not identity:
        raise ValueError("P12 private key/certificate does not match this profile, or certificate is invalid.")
    if entitlements.get("get-task-allow"):
        method = "debugging"
    elif profile.get("ProvisionsAllDevices"):
        method = "enterprise"
    elif profile.get("ProvisionedDevices"):
        method = "release-testing"
    else:
        raise ValueError("This is an App Store profile. Direct iPhone installation needs a development/ad hoc profile or a separate TestFlight pipeline.")
    return dict(team=team, bundle=bundle, uuid=profile["UUID"], identity=identity, method=method)


def main():
    task_temp = Path(os.environ["RUNNER_TEMP"])
    with (task_temp / "profile.plist").open("rb") as source:
        profile = plistlib.load(source)
    result = subprocess.run(
        ["security", "find-identity", "-v", "-p", "codesigning",
         str(task_temp / "visualgram-signing.keychain-db")],
        check=True, capture_output=True, text=True)
    identities = set(re.findall(r"\b[A-Fa-f0-9]{40}\b", result.stdout.upper()))
    values = metadata(profile, identities)
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
        for key, value in values.items():
            if "\n" in value or "\r" in value:
                raise ValueError("Invalid profile metadata.")
            output.write(f"{key}={value}\n")
    options = {
        "method": values["method"], "teamID": values["team"], "signingStyle": "manual",
        "signingCertificate": values["identity"],
        "provisioningProfiles": {values["bundle"]: values["uuid"]},
        "manageAppVersionAndBuildNumber": False,
    }
    with (task_temp / "ExportOptions.plist").open("wb") as output:
        plistlib.dump(options, output)
    print("Signing assets validated. Device must be permitted by the provisioning profile.")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError) as error:
        raise SystemExit(f"Signing configuration error: {error}") from None
