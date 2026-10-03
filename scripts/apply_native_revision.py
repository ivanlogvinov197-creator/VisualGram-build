"""Repair ordinary-gift instances and UI paths reported on iOS 26."""
from prepare_native import replace


def apply_revision(root):
    history = root / 'submodules/TelegramUI/Sources/ChatHistoryEntriesForView.swift'
    replace(history, 'peer: chatPeer, view: view, presentationData: presentationData)',
            'peer: chatPeer, accountPeer: associatedData.accountPeer, view: view, presentationData: presentationData)')

    # The account peer is available even in an empty history. The native service
    # formatter must see it as the author, not infer the sender from the chat peer.
    bubble = root / 'submodules/TelegramUI/Components/Chat/ChatMessageGiftBubbleContentNode/Sources/ChatMessageGiftBubbleContentNode.swift'
    replace(bubble, '                                        if let senderPeerId, let name = item.message.peers[senderPeerId].flatMap(EnginePeer.init)?.compactDisplayTitle {\n',
            '                                        if incoming, let senderPeerId, let name = item.message.peers[senderPeerId].flatMap(EnginePeer.init)?.compactDisplayTitle {\n')

    service = root / 'submodules/TelegramStringFormatting/Sources/ServiceMessageStrings.swift'
    text = service.read_text(encoding='utf-8')
    start = text.index('            case let .starGift(')
    end = text.index('            case let .paidMessagesRefunded(', start)
    gift_strings = text[start:end]
    old = 'message.author?.id == accountPeerId'
    if gift_strings.count(old) != 4:
        raise ValueError('Gift service-message layout changed')
    gift_strings = gift_strings.replace(old, '(message.author?.id == accountPeerId || (message.id.namespace == Int32.max - 42 && !message._asMessage().flags.contains(.Incoming)))')
    service.write_text(text[:start] + gift_strings + text[end:], encoding='utf-8', newline='\n')

    title = root / 'submodules/TelegramUI/Components/ChatTitleView/Sources/ChatTitleComponent.swift'
    replace(title, '                    if peerView.peerId.namespace == Namespaces.Peer.SecretChat {\n', '''                    let local = VisualGramLocalAppearance.shared.appearance(accountId: component.context.account.peerId, targetPeerId: peerView.peerId)
                    if local.enabled, peerView.peerId.namespace == Namespaces.Peer.CloudUser {
                        if local.verified { titleCredibilityIcon = .verified }
                        if local.premium, titleCredibilityIcon == .none { titleCredibilityIcon = .premium }
                        if local.overridesEmojiStatus, !hidePeerStatus {
                            if let status = local.emojiStatus, status.expirationDate.map({ $0 > Int32(Date().timeIntervalSince1970) }) ?? true {
                                titleStatusIcon = .emojiStatus(status)
                            } else { titleStatusIcon = .none }
                        }
                        if let verification = local.verification {
                            titleVerifiedIcon = .emojiStatus(PeerEmojiStatus(content: .emoji(fileId: verification.iconFileId), expirationDate: nil))
                        }
                    }
                    if peerView.peerId.namespace == Namespaces.Peer.SecretChat {
''')
    # Force a navigation-bar layout when only local presentation changes. Parent
    # ContentData/Component equality intentionally ignores server-unchanged peers.
    replace(title, '    private let parentTitleState = ComponentState()\n', '    private let parentTitleState = ComponentState()\n    private let visualGramNavigationDisposable = MetaDisposable()\n    private var visualGramContext: AccountContext?\n')
    replace(title, '        self.ignoreParentTransitionRequests = ignoreParentTransitionRequests\n', '''        if self.visualGramContext !== context {
            self.visualGramContext = context
            self.visualGramNavigationDisposable.set((VisualGramLocalAppearance.shared.changes |> deliverOnMainQueue).start(next: { [weak self] _ in
                self?.title.view?.setNeedsLayout()
                self?.requestUpdate?(.immediate)
            }))
        }
        self.ignoreParentTransitionRequests = ignoreParentTransitionRequests
''')
    replace(title, '    required public init?(coder: NSCoder) {\n', '    deinit { self.visualGramNavigationDisposable.dispose() }\n\n    required public init?(coder: NSCoder) {\n')

    for relative in [
        'submodules/TelegramUI/Components/Gifts/GiftStoreScreen/Sources/BalanceComponent.swift',
        'submodules/TelegramUI/Components/Stars/StarsBalanceOverlayComponent/Sources/StarsBalanceOverlayComponent.swift'
    ]:
        path = root / relative
        replace(path, 'if let starsContext = component.context.starsContext, let tonContext = component.context.tonContext {', 'do {')
        replace(path, 'starsContext.state,', 'component.context.starsContext?.state ?? .single(nil),')
        replace(path, 'tonContext.state,', 'component.context.tonContext?.state ?? .single(nil),')
        # Local Stars remain available while the real balance/TON is loading.
        local_condition = 'localBalance.enabled' if 'GiftStoreScreen' in relative else 'component.peerId == component.context.account.peerId && localBalance.enabled'
        replace(path, '            let presentationData = component.context.sharedContext.currentPresentationData.with { $0 }\n', f'''            let localBalance = VisualGramLocalAppearance.shared.appearance(accountId: component.context.account.peerId)
            if {local_condition}, let stars = localBalance.stars {{ self.starsBalance = stars }}
            let presentationData = component.context.sharedContext.currentPresentationData.with {{ $0 }}
''')

    gift = root / 'submodules/TelegramUI/Components/Gifts/GiftViewScreen/Sources/GiftViewScreen.swift'
    # Catalog purchases must not be hidden by ownership of another user's local
    # copy or by incoming=true in a native preview. Commit still checks ownership.
    replace(gift, '        fileprivate var visualGramCanManage: Bool {\n', '''        fileprivate var visualGramCatalogPurchase: Bool {
            guard case let .uniqueGift(gift, _) = self.subject,
                  gift.resellAmounts?.contains(where: { $0.currency == .stars && $0.amount.value > 0 }) == true else { return false }
            let appearance = VisualGramLocalAppearance.shared.appearance(accountId: self.context.account.peerId)
            guard (appearance.enabled && appearance.stars != nil) || self.visualGramReference != nil else { return false }
            if case let .peerId(owner) = gift.owner, owner == self.context.account.peerId { return false }
            return true
        }

        fileprivate var visualGramCanManage: Bool {
''')
    replace(gift, '            if state.isVisualGramGift {\n                incoming = state.visualGramCanManage\n', '            if state.visualGramCatalogPurchase {\n                incoming = false\n                isMyOwnedUniqueGift = false\n                isMyHostedUniqueGift = false\n                isChannelGift = false\n                canGiftUpgrade = false\n                canUpgrade = false\n            } else if state.isVisualGramGift {\n                incoming = state.visualGramCanManage\n')
    replace(gift, 'if uniqueGift.resellForTonOnly {\n', 'if uniqueGift.resellForTonOnly && !state.visualGramCatalogPurchase {\n')
    replace(gift, '            } else if !incoming, let resellAmount, !isMyOwnedUniqueGift {\n', '            } else if (!incoming || state.visualGramCatalogPurchase), let resellAmount, !isMyOwnedUniqueGift {\n')
