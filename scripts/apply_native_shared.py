"""Shared device presentation: stock chat badges and the three NFT header buttons."""
from prepare_native import replace


def apply_shared(root):
    title = root / "submodules/TelegramUI/Components/ChatTitleView/Sources/ChatTitleView.swift"
    replace(title, '    public var titleContent: ChatTitleContent? {\n', '    private let visualGramAppearanceDisposable = MetaDisposable()\n\n    public var titleContent: ChatTitleContent? {\n')
    replace(title, '                            if let peer = peerView.peer {\n', '''                            if let original = peerView.peer {
                                let peer = VisualGramLocalAppearance.shared.displayPeer(EnginePeer(original), accountId: self.context.account.peerId)?._asPeer() ?? original
''')
    replace(title, '        self.button.view.addGestureRecognizer(UILongPressGestureRecognizer(target: self, action: #selector(self.longPressGesture(_:))))\n', '''        self.button.view.addGestureRecognizer(UILongPressGestureRecognizer(target: self, action: #selector(self.longPressGesture(_:))))
        self.visualGramAppearanceDisposable.set((VisualGramLocalAppearance.shared.changes |> deliverOnMainQueue).start(next: { [weak self] _ in
            guard let self else { return }
            let content = self.titleContent
            self.titleContent = content
            self.requestUpdate?(.immediate)
        }))
''')
    replace(title, '    required public init?(coder aDecoder: NSCoder) {\n', '    deinit { self.visualGramAppearanceDisposable.dispose() }\n\n    required public init?(coder aDecoder: NSCoder) {\n')

    item = root / "submodules/ChatListUI/Sources/Node/ChatListItem.swift"
    replace(item, '                        if let peer = iconPeer {\n', '                        if let peer = VisualGramLocalAppearance.shared.displayPeer(iconPeer, accountId: item.context.account.peerId) {\n')
    replace(item, '                } else if case let .chat(itemPeer) = contentPeer, let peer = itemPeer.chatOrMonoforumMainPeer {\n', '''                } else if case let .chat(itemPeer) = contentPeer, let original = itemPeer.chatOrMonoforumMainPeer {
                    let peer = VisualGramLocalAppearance.shared.displayPeer(original, accountId: item.context.account.peerId) ?? original
''')
    replace(item, '    private var cachedDataDisposable = MetaDisposable()\n', '    private var cachedDataDisposable = MetaDisposable()\n    private let visualGramAppearanceDisposable = MetaDisposable()\n')
    replace(item, '        self.peerPresenceManager = PeerPresenceStatusManager(update: { [weak self] in\n', '''        self.visualGramAppearanceDisposable.set((VisualGramLocalAppearance.shared.changes |> deliverOnMainQueue).start(next: { [weak self] _ in
            guard let self, let params = self.layoutParams else { return }
            let (_, apply) = self.asyncLayout()(params.0, params.6, params.1, params.2, params.3, params.4, params.5)
            apply(false, false)
        }))
        self.peerPresenceManager = PeerPresenceStatusManager(update: { [weak self] in
''')
    replace(item, '        self.cachedDataDisposable.dispose()\n', '        self.cachedDataDisposable.dispose()\n        self.visualGramAppearanceDisposable.dispose()\n')

    gift = root / "submodules/TelegramUI/Components/Gifts/GiftViewScreen/Sources/GiftViewScreen.swift"
    replace(gift, '        private var isVisualGramGift: Bool {\n', '        fileprivate var isVisualGramGift: Bool {\n')
    replace(gift, 'visualGramGiftHasPremium(context: component.context)', 'visualGramGiftHasPremium(context: component.context, localGift: state.isVisualGramGift)', expected=2)
    replace(gift, 'private func visualGramGiftHasPremium(context: AccountContext) -> Bool {', 'private func visualGramGiftHasPremium(context: AccountContext, localGift: Bool = false) -> Bool {')
    replace(gift, '    return context.isPremium || (appearance.enabled && appearance.premium)\n', '    return localGift || context.isPremium || (appearance.enabled && appearance.premium)\n')
    replace(gift, '            let wearOwnerPeerId = ownerPeerId ?? component.context.account.peerId\n', '''            let wearOwnerPeerId: EnginePeer.Id
            if VisualGramLocalAppearance.isLocalReference(subject.arguments?.reference), let gift = uniqueGift, case let .peerId(id) = gift.owner { wearOwnerPeerId = id }
            else { wearOwnerPeerId = ownerPeerId ?? component.context.account.peerId }
''')
    replace(gift, '                                if peer.id == component.context.account.peerId, peer.isPremium {\n', '                                if peer.isPremium && (peer.id == component.context.account.peerId || VisualGramLocalAppearance.isLocalReference(subject.arguments?.reference)) {\n')
    replace(gift, '                savedToProfile = arguments.savedToProfile\n', '''                if uniqueGift != nil, VisualGramLocalAppearance.isLocalReference(arguments.reference) {
                    isMyOwnedUniqueGift = true
                }
                savedToProfile = arguments.savedToProfile
''')
    replace(gift, '                        var buttonsCount = 1\n', '''                        if VisualGramLocalAppearance.isLocalReference(subject.arguments?.reference) { canTransfer = true; canResell = true }
                        var buttonsCount = 1
''')
    for signature, text in [('transferGift()', 'Передача доступна для настоящих подарков.'), ('resellGift(update: Bool = false)', 'Продажа доступна для настоящих подарков.')]:
        replace(gift, f'        func {signature} {{\n            guard !self.isVisualGramGift else {{ return }}\n', f'''        func {signature} {{
            if self.isVisualGramGift {{
                self.showAttributeInfo(tag: self.statusTag, text: "{text}")
                return
            }}
''')
    replace(gift, '''            if self.isVisualGramGift {
                VisualGramLocalAppearance.shared.update(accountId: self.context.account.peerId) { $0.enabled = true; $0.premium = true }
            }
''', '''            if self.isVisualGramGift {
                let owner: EnginePeer.Id
                if case let .peerId(id) = uniqueGift.owner { owner = id } else { owner = self.context.account.peerId }
                VisualGramLocalAppearance.shared.update(accountId: self.context.account.peerId, targetPeerId: owner) { $0.enabled = true; $0.premium = true }
                _ = VisualGramLocalAppearance.shared.setLocalGiftStatus(accountId: self.context.account.peerId, targetPeerId: owner, gift: uniqueGift, expirationDate: nil)
                self.pendingWear = true; self.pendingTakeOff = false; self.inWearPreview = false
                self.updated(transition: .spring(duration: 0.4))
                return
            }
''')
    replace(gift, '''            if self.isVisualGramGift {
                VisualGramLocalAppearance.shared.update(accountId: self.context.account.peerId) { $0.enabled = true }
            }
''', '''            if self.isVisualGramGift {
                var owner = self.context.account.peerId
                if let gift = self.subject.arguments?.gift, case let .unique(unique) = gift, case let .peerId(id) = unique.owner { owner = id }
                _ = VisualGramLocalAppearance.shared.setLocalEmojiStatus(accountId: self.context.account.peerId, targetPeerId: owner, status: nil)
                self.pendingTakeOff = true; self.pendingWear = false
                self.updated(transition: .spring(duration: 0.4))
                return
            }
''')
