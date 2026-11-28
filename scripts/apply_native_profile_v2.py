"""Install the optional moving NFT bubbles in the native profile header."""
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
    replace(source, '                let dateTimeFormat = component.context.sharedContext.currentPresentationData.with { $0 }.dateTimeFormat', """                if let bubbles = self.visualGramBubbles {
                    return bubbles.accessibleGifts
                }
                let dateTimeFormat = component.context.sharedContext.currentPresentationData.with { $0 }.dateTimeFormat""")
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
    replace(source, 'private class GiftIconLayer: SimpleLayer {', '''func makeVisualGramGiftIconLayer(context: AccountContext, gift: ProfileGiftsContext.State.StarGift, size: CGSize) -> CALayer {
    return GiftIconLayer(context: context, gift: gift, size: size, glowing: false)
}

private class GiftIconLayer: SimpleLayer {''')

    header = peer / "PeerInfoScreen/Sources/PeerInfoHeaderNode.swift"
    replace(header, '    let giftsCover = ComponentView<Empty>()\n', '''    let giftsCover = ComponentView<Empty>()
    private var visualGramGiftsCoverOnTop = false
''')
    replace(header, '        let buttonSpacing: CGFloat = 8.0', """        let profileV2Enabled = !isSettings && !state.isEditing && !isMediaOnly && !self.isAvatarExpanded && (VisualGramLocalAppearance.shared.appearance(accountId: self.context.account.peerId).profileV2Enabled ?? false)
        let buttonSpacing: CGFloat = 8.0""")
    replace(header, '                containerSize: CGSize(width: width, height: apparentBackgroundHeight)\n', '                containerSize: CGSize(width: width, height: profileV2Enabled ? containerHeight : apparentBackgroundHeight)\n')
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
    replace(header, '        let setByFrame = self.avatarListNode.listContainerNode.setByYouNode.view.convert(', """        if self.visualGramGiftsCoverOnTop, let cover = self.giftsCover.view, cover.alpha > 0.01,
           let hit = cover.hitTest(self.view.convert(point, to: cover), with: event) {
            return hit
        }
        let setByFrame = self.avatarListNode.listContainerNode.setByYouNode.view.convert(""")
    # The currentState snapshot only contains server gifts. Use the exact item hit
    # in the merged profile state, preserving local variants and references.
    replace(header, 'var openUniqueGift: ((UIView, String) -> Void)?', 'var openUniqueGift: ((UIView, String, ProfileGiftsContext.State.StarGift?) -> Void)?')
    replace(header, 'IconView, uniqueGiftSlug)', 'IconView, uniqueGiftSlug, nil)', expected=2)
    replace(header, 'guard let self, case let .unique(gift) = gift.gift else', 'guard let self, case let .unique(uniqueGift) = gift.gift else')
    replace(header, 'self.openUniqueGift?(self.view, gift.slug)', 'self.openUniqueGift?(self.view, uniqueGift.slug, gift)')
    screen = peer / "PeerInfoScreen/Sources/PeerInfoScreen.swift"
    replace(screen, 'self.headerNode.openUniqueGift = { [weak self] _, slug in', 'self.headerNode.openUniqueGift = { [weak self] _, slug, selectedGift in')
    replace(screen, '            if let state = profileGifts.currentState {\n                for gift in state.gifts {', '            if let candidates = selectedGift.map({ [$0] }) ?? profileGifts.currentState?.gifts {\n                for gift in candidates {')
    replace(cover / "Sources/PeerInfoCoverComponent.swift", 'private final class PatternContentsTarget:', 'final class PatternContentsTarget:')
    button = peer / "PeerInfoScreen/Sources/PeerInfoHeaderButtonNode.swift"
    replace(header, 'text: buttonText, icon: buttonIcon, isActive: isActive,', 'text: buttonText, icon: buttonIcon, usesRoundIcon: profileV2Enabled, isActive: isActive,')
    replace(button, 'text: String, icon: PeerInfoHeaderButtonIcon, isActive:', 'text: String, icon: PeerInfoHeaderButtonIcon, usesRoundIcon: Bool = false, isActive:')
    replace(button, '        let backgroundFrame = CGRect(origin: CGPoint(x: 0.0, y: backgroundY), size: CGSize(width: size.width, height: max(0.0, size.height - backgroundY)))', """
        let disc = min(40.0, size.width)
        let backgroundFrame: CGRect
        if usesRoundIcon {
            let diameter = disc * fraction
            backgroundFrame = CGRect(x: (size.width - diameter) * 0.5, y: backgroundY + (disc - diameter) * 0.5, width: diameter, height: diameter)
        } else {
            backgroundFrame = CGRect(origin: CGPoint(x: 0.0, y: backgroundY), size: CGSize(width: size.width, height: max(0.0, size.height - backgroundY)))
        }
        let radius = usesRoundIcon ? backgroundFrame.height * 0.5 : min(16.0, backgroundFrame.height * 0.5)""")
    replace(button, 'cornerRadius: min(16.0, backgroundFrame.height * 0.5)', 'cornerRadius: radius', expected=2)
    replace(button, 'y: size.height - titleSize.height - 9.0', 'y: usesRoundIcon ? size.height - titleSize.height : size.height - titleSize.height - 9.0')
    for name in ("VisualGramProfileGiftBubbles.swift", "VisualGramProfileGiftMotion.swift"):
        shutil.copyfile(project / "native" / name, cover / "Sources" / name)
