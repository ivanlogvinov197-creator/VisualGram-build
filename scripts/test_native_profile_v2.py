"""Run the profile bubble physics checks against the installed source files."""
from pathlib import Path
import argparse
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("--swiftc", default="swiftc")
    args = parser.parse_args()
    peer = args.source / "submodules/TelegramUI/Components/PeerInfo"
    cover = peer / "PeerInfoCoverComponent/Sources"
    screen = peer / "PeerInfoScreen/Sources"
    with tempfile.TemporaryDirectory() as directory:
        directory = Path(directory)
        output = directory / "ProfileGiftMotionTests"
        subprocess.run([args.swiftc, "-warnings-as-errors", str(cover / "VisualGramProfileGiftMotion.swift"),
                        str(Path(__file__).with_name("ProfileGiftMotionTests.swift")), "-o", str(output)], check=True)
        subprocess.run([str(output)], check=True)
    subprocess.run([args.swiftc, "-frontend", "-parse", *map(str, [
        cover / "PeerInfoGiftsCoverComponent.swift", cover / "VisualGramProfileGiftBubbles.swift",
        cover / "PeerInfoCoverComponent.swift", screen / "PeerInfoScreen.swift",
        screen / "PeerInfoHeaderButtonNode.swift", screen / "PeerInfoHeaderNode.swift",
        args.source / "submodules/TelegramUI/Components/Gifts/GiftViewScreen/Sources/GiftUpgradeVariantsScreen.swift",
    ])], check=True)


if __name__ == "__main__":
    main()
