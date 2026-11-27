"""Install the optional moving NFT bubbles in the native profile header."""
import argparse
from pathlib import Path
import shutil

from prepare_native import replace


def apply_profile_v2(root, project):
    peer = root / "submodules/TelegramUI/Components/PeerInfo"
    cover = peer / "PeerInfoCoverComponent"
    source = cover / "Sources/PeerInfoGiftsCoverComponent.swift"
    replace(cover / "BUILD", '    deps = [\n', '''    deps = [
        "//submodules/TelegramUI/Components/GlassBackgroundComponent",
''')
    replace(source, '    public let hasBackground: Bool\n', '''    public let hasBackground: Bool
    public let visualGramProfileV2Enabled: Bool
''')
    replace(source, '        hasBackground: Bool,\n', '''        hasBackground: Bool,
        visualGramProfileV2Enabled: Bool = false,
''')
    replace(source, '        self.giftsContext = giftsContext\n', '''        self.giftsContext = giftsContext
        self.visualGramProfileV2Enabled = visualGramProfileV2Enabled
''')
    replace(source, '        if lhs.hasBackground != rhs.hasBackground {\n', '''        if lhs.hasBackground != rhs.hasBackground || lhs.visualGramProfileV2Enabled != rhs.visualGramProfileV2Enabled {
''')
    replace(source, '        private var iconLayers: [AnyHashable: GiftIconLayer] = [:]\n', '''        private var iconLayers: [AnyHashable: GiftIconLayer] = [:]
        private var visualGramBubbles: VisualGramProfileGiftBubbles?
        private lazy var legacyTap = UITapGestureRecognizer(target: self, action: #selector(self.tapped(_:)))
''')
    replace(source, '            self.addGestureRecognizer(UITapGestureRecognizer(target: self, action: #selector(self.tapped(_:))))',
            '            self.addGestureRecognizer(self.legacyTap)')
    replace(source, '        public override func point(inside point: CGPoint, with event: UIEvent?) -> Bool {\n', '''        public override func point(inside point: CGPoint, with event: UIEvent?) -> Bool {
            if let bubbles = self.visualGramBubbles {
                return bubbles.point(inside: self.convert(point, to: bubbles), with: event)
            }
''')
    replace(source, '            if !giftIds.isEmpty && (self.iconPositions.isEmpty', '            if !component.visualGramProfileV2Enabled && !giftIds.isEmpty && (self.iconPositions.isEmpty')
    replace(source, '            var validIds = Set<AnyHashable>()\n            var index = 0\n            for gift in self.gifts.prefix(12) {', '''            if component.visualGramProfileV2Enabled {
                for layer in self.iconLayers.values {
                    layer.removeFromSuperlayer()
                }
                self.iconLayers.removeAll()
                self.iconPositions.removeAll()

                let bubbles: VisualGramProfileGiftBubbles
                if let current = self.visualGramBubbles {
                    bubbles = current
                } else {
                    self.legacyTap.isEnabled = false
                    bubbles = VisualGramProfileGiftBubbles(frame: .zero)
                    self.visualGramBubbles = bubbles
                    self.addSubview(bubbles)
                }
                bubbles.frame = CGRect(origin: .zero, size: availableSize)
                bubbles.update(component: component, gifts: self.gifts)
                return availableSize
            }
            if let bubbles = self.visualGramBubbles {
                bubbles.removeFromSuperview()
                self.visualGramBubbles = nil
                self.legacyTap.isEnabled = true
            }

            var validIds = Set<AnyHashable>()
            var index = 0
            for gift in self.gifts.prefix(12) {''')
    replace(source, 'private class GiftIconLayer: SimpleLayer {', 'final class GiftIconLayer: SimpleLayer {')

    header = peer / "PeerInfoScreen/Sources/PeerInfoHeaderNode.swift"
    replace(header, '    let giftsCover = ComponentView<Empty>()\n', '''    let giftsCover = ComponentView<Empty>()
    private var visualGramGiftsCoverOnTop = false
''')
    replace(header, '        if let profileGiftsContext, let peer {\n            let giftsCoverSize = self.giftsCover.update(', '''        if let profileGiftsContext, let peer {
            let profileV2Enabled = !isSettings && !state.isEditing && (VisualGramLocalAppearance.shared.appearance(accountId: self.context.account.peerId).profileV2Enabled ?? false)
            let giftsCoverSize = self.giftsCover.update(''')
    replace(header, '                    giftsContext: profileGiftsContext,\n                    hasBackground: hasBackground,\n', '''                    giftsContext: profileGiftsContext,
                    hasBackground: hasBackground,
                    visualGramProfileV2Enabled: profileV2Enabled,
''')
    replace(header, '''                if giftsCoverView.superview == nil {
                    self.view.insertSubview(giftsCoverView, aboveSubview: self.backgroundBannerView)
                }
''', '''                if giftsCoverView.superview == nil || self.visualGramGiftsCoverOnTop != profileV2Enabled {
                    let anchorView = profileV2Enabled ? self.regularContentNode.view : self.backgroundBannerView
                    self.view.insertSubview(giftsCoverView, aboveSubview: anchorView)
                    self.visualGramGiftsCoverOnTop = profileV2Enabled
                }
''')
    replace(header, '''        if let giftsCoverView = self.giftsCover.view, giftsCoverView.alpha > 0.0, giftsCoverView.point(inside: self.view.convert(point, to: giftsCoverView), with: event) {
            return giftsCoverView
        }
''', '''        if let giftsCoverView = self.giftsCover.view, giftsCoverView.alpha > 0.0 {
            let coverPoint = self.view.convert(point, to: giftsCoverView)
            if giftsCoverView.point(inside: coverPoint, with: event) {
                if self.visualGramGiftsCoverOnTop {
                    return giftsCoverView.hitTest(coverPoint, with: event)
                }
                return giftsCoverView
            }
        }
''')
    shutil.copyfile(project / "native/VisualGramProfileGiftBubbles.swift", cover / "Sources/VisualGramProfileGiftBubbles.swift")


def add_legacy_toggle(root):
    store = root / "submodules/TelegramCore/Sources/VisualGramLocalAppearance.swift"
    menu = root / "submodules/TelegramUI/Components/PeerInfo/PeerInfoScreen/Sources/VisualGramAppearanceController.swift"
    if 'public var profileV2Enabled: Bool?' not in store.read_text(encoding="utf-8"):
        replace(store, 'public struct VisualGramAppearance: Codable, Equatable {\n', '''public struct VisualGramAppearance: Codable, Equatable {
    public var profileV2Enabled: Bool?
''')
    if '"Profile V2"' not in menu.read_text(encoding="utf-8"):
        replace(menu, '    func toggle(_ id: Int32, value: Bool) {\n', '''    func toggle(_ id: Int32, value: Bool) {
        if id == 904 {
            VisualGramLocalAppearance.shared.update(accountId: self.context.account.peerId) { $0.profileV2Enabled = value }
            return
        }
''')
        replace(menu, '        entries.sort()\n', '''        let accountAppearance = VisualGramLocalAppearance.shared.appearance(accountId: context.account.peerId)
        add(904, 0, "Profile V2", .toggle(accountAppearance.profileV2Enabled ?? false))
        entries.sort()
''')


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Add Profile V2 to an existing VisualGram native checkout.")
    parser.add_argument("source", type=Path, help="Telegram source with the VisualGram appearance patches already applied")
    source = parser.parse_args().source
    add_legacy_toggle(source)
    apply_profile_v2(source, Path(__file__).resolve().parents[1])
