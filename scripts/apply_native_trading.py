"""Fix local upgrades and modern chat titles; implement local NFT ownership and market."""
from prepare_native import replace


def apply_trading(root):
    title = root / 'submodules/TelegramUI/Components/ChatTitleView/Sources/ChatTitleComponent.swift'
    replace(title, 'import Foundation\n', 'import Foundation\nimport SwiftSignalKit\n')
    replace(title, '                    if let peer = peerView.peer {\n                        if let customTitle', '''                    if let original = peerView.peer {
                        let peer = VisualGramLocalAppearance.shared.displayPeer(EnginePeer(original), accountId: component.context.account.peerId)?._asPeer() ?? original
                        if let customTitle''')
    replace(title, '        private var presenceManager: PeerPresenceStatusManager?\n', '        private var presenceManager: PeerPresenceStatusManager?\n        private let visualGramDisposable = MetaDisposable()\n')
    replace(title, '            self.presenceManager = PeerPresenceStatusManager(update: { [weak self] in\n', '''            self.visualGramDisposable.set((VisualGramLocalAppearance.shared.changes |> deliverOnMainQueue).start(next: { [weak self] _ in
                self?.state?.updated(transition: .immediate)
            }))
            self.presenceManager = PeerPresenceStatusManager(update: { [weak self] in
''')
    replace(title, '        required init?(coder: NSCoder) {\n', '        deinit { self.visualGramDisposable.dispose() }\n\n        required init?(coder: NSCoder) {\n')

    core = root / 'submodules/TelegramCore/Sources/TelegramEngine/Payments/StarGifts.swift'
    signature = 'func _internal_transferStarGift(account: Account, prepaid: Bool, reference: StarGiftReference, peerId: EnginePeer.Id) -> Signal<Never, TransferStarGiftError> {\n'
    replace(core, signature, signature + '''    if VisualGramLocalAppearance.isLocalReference(reference) {
        return VisualGramLocalAppearance.shared.transferLocalGift(accountId: account.peerId, reference: reference, recipientPeerId: peerId, now: Int32(clamping: Int64(Date().timeIntervalSince1970))) ? .complete() : .fail(.generic)
    }
''')
    signature = 'func _internal_updateStarGiftResalePrice(account: Account, reference: StarGiftReference, price: CurrencyAmount?) -> Signal<Never, UpdateStarGiftPriceError> {\n'
    replace(core, signature, signature + '''    if VisualGramLocalAppearance.isLocalReference(reference) {
        guard price == nil || price?.currency == .stars else { return .fail(.generic) }
        return VisualGramLocalAppearance.shared.listLocalGift(accountId: account.peerId, reference: reference, price: price?.amount.value) ? .complete() : .fail(.generic)
    }
''')
    # Scope these replacements to the public resale context, not other contexts with similar state APIs.
    text = core.read_text(encoding='utf-8')
    start = text.index('public final class ResaleGiftsContext {')
    resale = text[start:]
    resale = resale.replace('    private let queue: Queue = .mainQueue()\n', '    private let visualGramAccount: Account\n    private let visualGramGiftId: Int64\n    private let queue: Queue = .mainQueue()\n', 1)
    resale = resale.replace('    public var state: Signal<ResaleGiftsContext.State, NoError> {\n        return Signal { subscriber in', '    public var state: Signal<ResaleGiftsContext.State, NoError> {\n        return combineLatest(self.visualGramServerState, VisualGramLocalAppearance.shared.changes) |> map { state, _ in\n            VisualGramLocalAppearance.shared.localMarketState(state, giftId: self.visualGramGiftId, accountId: self.visualGramAccount.peerId)\n        }\n    }\n\n    private var visualGramServerState: Signal<ResaleGiftsContext.State, NoError> {\n        return Signal { subscriber in', 1)
    resale = resale.replace('        self.forCrafting = forCrafting\n', '        self.visualGramAccount = account\n        self.visualGramGiftId = giftId\n        self.forCrafting = forCrafting\n', 1)
    resale = resale.replace('    public func updateStarGiftResellPrice(slug: String, price: CurrencyAmount?) -> Signal<Never, UpdateStarGiftPriceError> {\n', '''    public func updateStarGiftResellPrice(slug: String, price: CurrencyAmount?) -> Signal<Never, UpdateStarGiftPriceError> {
        if let reference = VisualGramLocalAppearance.shared.localReference(slug: slug) {
            guard price == nil || price?.currency == .stars else { return .fail(.generic) }
            return VisualGramLocalAppearance.shared.listLocalGift(accountId: self.visualGramAccount.peerId, reference: reference, price: price?.amount.value) ? .complete() : .fail(.generic)
        }
''', 1)
    resale = resale.replace('        return state\n    }\n}', '        return state.map { VisualGramLocalAppearance.shared.localMarketState($0, giftId: self.visualGramGiftId, accountId: self.visualGramAccount.peerId) }\n    }\n}', 1)
    core.write_text(text[:start] + resale, encoding='utf-8')

    pane = root / 'submodules/TelegramUI/Components/PeerInfo/PeerInfoVisualMediaPaneNode/Sources/PeerInfoGiftsPaneNode.swift'
    replace(pane, '        let canManage = self.peerId == self.context.account.peerId || self.canManage || VisualGramLocalAppearance.isLocalReference(gift.reference)\n', '        let canManage = VisualGramLocalAppearance.isLocalReference(gift.reference) ? VisualGramLocalAppearance.shared.canManageLocalGift(accountId: self.context.account.peerId, reference: gift.reference) : (self.peerId == self.context.account.peerId || self.canManage)\n')
    replace(pane, '            if case let .unique(uniqueGift) = gift.gift, self.peerId == self.context.account.peerId || VisualGramLocalAppearance.isLocalReference(gift.reference) {\n', '            if case let .unique(uniqueGift) = gift.gift, canManage {\n')

    screen = root / 'submodules/TelegramUI/Components/Gifts/GiftViewScreen/Sources/GiftViewScreen.swift'
    replace(screen, '        fileprivate var isVisualGramGift: Bool {\n', '''        fileprivate var visualGramReference: StarGiftReference? {
            if case let .message(message) = self.subject, message.id.namespace == Int32.max - 42 {
                return VisualGramLocalAppearance.shared.localReference(messageId: message.id)
            }
            if VisualGramLocalAppearance.isLocalReference(self.subject.arguments?.reference) { return self.subject.arguments?.reference }
            if case let .unique(gift) = self.subject.arguments?.gift { return VisualGramLocalAppearance.shared.localReference(slug: gift.slug) }
            return nil
        }

        fileprivate var visualGramCanManage: Bool {
            return VisualGramLocalAppearance.shared.canManageLocalGift(accountId: self.context.account.peerId, reference: self.visualGramReference)
        }

        fileprivate var isVisualGramGift: Bool {
            if self.visualGramReference != nil { return true }
''')
    replace(screen, '                    if arguments.canUpgrade || arguments.upgradeStars != nil || arguments.prepaidUpgradeHash != nil {\n', '                    if arguments.canUpgrade || arguments.upgradeStars != nil || arguments.prepaidUpgradeHash != nil || self.visualGramCanManage {\n')
    replace(screen, '''                        self.upgradePreviewDisposable.add((context.engine.payments.starGiftUpgradePreview(giftId: gift.id)
                        |> deliverOnMainQueue).start(next: { [weak self] upgradePreview in
                            guard let self, let upgradePreview else {
                                return
                            }
''', '''                        self.upgradePreviewDisposable.add((context.engine.payments.starGiftUpgradePreview(giftId: gift.id)
                        |> deliverOnMainQueue).start(next: { [weak self] upgradePreview in
                            guard let self else { return }
                            guard let upgradePreview else {
                                self.inProgress = false
                                self.scheduledUpgradePreview = false
                                self.updated()
                                if self.isVisualGramGift { self.showAttributeInfo(tag: self.statusTag, text: "Не удалось загрузить улучшение. Попробуй открыть подарок ещё раз.") }
                                return
                            }
''')
    replace(screen, '        func requestUpgradePreview() {\n', '''        func requestUpgradePreview() {
            if self.isVisualGramGift {
                guard self.visualGramCanManage else { return }
                if self.upgradePreview == nil, case let .generic(gift) = self.subject.arguments?.gift {
                    guard !self.inProgress else { return }
                    self.inProgress = true
                    self.updated()
                    self.upgradePreviewDisposable.add((self.context.engine.payments.starGiftUpgradePreview(giftId: gift.id) |> deliverOnMainQueue).start(next: { [weak self] preview in
                        guard let self else { return }
                        self.inProgress = false
                        self.scheduledUpgradePreview = false
                        guard let preview else {
                            self.updated()
                            self.showAttributeInfo(tag: self.statusTag, text: "Улучшение пока недоступно. Попробуй ещё раз.")
                            return
                        }
                        self.upgradePreview = preview
                        for attribute in preview.attributes {
                            switch attribute {
                            case let .model(_, file, _, _), let .pattern(_, file, _):
                                self.upgradePreviewDisposable.add(freeMediaFileResourceInteractiveFetched(account: self.context.account, userLocation: .other, fileReference: .standalone(media: file), resource: file.resource).start())
                            default: break
                            }
                        }
                        self.requestUpgradePreview()
                    }))
                    return
                }
            }
''')
    replace(screen, '                guard !self.inProgress, let reference = arguments.reference,\n', '                guard !self.inProgress, self.visualGramCanManage, let reference = self.visualGramReference,\n')
    replace(screen, '''            if VisualGramLocalAppearance.isLocalReference(subject.arguments?.reference) {
                incoming = true
                canGiftUpgrade = false
            }
''', '''            if state.isVisualGramGift {
                incoming = state.visualGramCanManage
                isMyOwnedUniqueGift = uniqueGift != nil && state.visualGramCanManage
                isMyHostedUniqueGift = false
                isChannelGift = false
                canGiftUpgrade = false
                if !state.visualGramCanManage { canUpgrade = false }
            }
''')
    replace(screen, '            if !canUpgrade, let gift = state.starGiftsMap[giftId], let _ = gift.upgradeStars {\n', '            if !canUpgrade, (!state.isVisualGramGift || state.visualGramCanManage), let gift = state.starGiftsMap[giftId], let _ = gift.upgradeStars {\n')
    replace(screen, '                        if VisualGramLocalAppearance.isLocalReference(subject.arguments?.reference) { canTransfer = true; canResell = true }\n', '                        if state.isVisualGramGift { canTransfer = state.visualGramCanManage; canResell = state.visualGramCanManage }\n')
    replace(screen, '''            if self.isVisualGramGift {
                self.showAttributeInfo(tag: self.statusTag, text: "Передача доступна для настоящих подарков.")
                return
            }
''', '''            if self.isVisualGramGift {
                guard self.visualGramCanManage, let reference = self.visualGramReference,
                      case let .unique(gift) = self.subject.arguments?.gift,
                      let controller = self.getController() as? GiftViewScreen else { return }
                let context = self.context
                let _ = (context.account.stateManager.contactBirthdays |> take(1) |> deliverOnMainQueue).start(next: { [weak self, weak controller] birthdays in
                    guard let self, let controller else { return }
                    let picker = context.sharedContext.makePremiumGiftController(context: context, source: .starGiftTransfer(birthdays, reference, gift, 0, nil, false), completion: { [weak self, weak controller] peerIds in
                        guard let self, let recipient = peerIds.first else { return .complete() }
                        guard VisualGramLocalAppearance.shared.transferLocalGift(accountId: context.account.peerId, reference: reference, recipientPeerId: recipient, now: Int32(clamping: Int64(Date().timeIntervalSince1970))) else {
                            self.showAttributeInfo(tag: self.statusTag, text: "Подарок больше не принадлежит этому аккаунту.")
                            return .complete()
                        }
                        self.updated(transition: .immediate)
                        controller?.dismissAnimated()
                        return .complete()
                    })
                    controller.push(picker)
                })
                return
            }
''')
    replace(screen, '''            if self.isVisualGramGift {
                self.showAttributeInfo(tag: self.statusTag, text: "Продажа доступна для настоящих подарков.")
                return
            }
''', '''            if self.isVisualGramGift && !self.visualGramCanManage { return }
''')
    # A native resale UI supplies the local reference; its Core boundary commits locally.
    replace(screen, '            let reference = arguments.reference ?? .slug(slug: gift.slug)\n', '            let reference = self.visualGramReference ?? arguments.reference ?? .slug(slug: gift.slug)\n')
    replace(screen, '                let owner: EnginePeer.Id\n', '                guard self.visualGramCanManage else { return }\n                let owner: EnginePeer.Id\n')
    replace(screen, '                var owner = self.context.account.peerId\n', '                guard self.visualGramCanManage else { return }\n                var owner = self.context.account.peerId\n')
    replace(screen, '''        func commitBuy(acceptedPrice: CurrencyAmount? = nil, skipConfirmation: Bool = false) {
            guard !self.isVisualGramGift else { return }
''', '''        func commitBuy(acceptedPrice: CurrencyAmount? = nil, skipConfirmation: Bool = false) {
            if case let .unique(gift) = self.subject.arguments?.gift, visualGramBuyLocalGift(context: self.context, recipientPeerId: self.recipientPeerId ?? self.context.account.peerId, gift: gift, getController: self.getController, completion: { [weak self] in
                (self?.getController() as? GiftViewScreen)?.animateSuccess()
                (self?.getController() as? GiftViewScreen)?.dismissAnimated()
            }) { return }
            guard !self.isVisualGramGift else { return }
''')
    # Do not fetch server payment forms for a local listing or local catalog purchase.
    replace(screen, '                    if let _ = arguments.resellAmounts, !isOwn {\n', '                    if let _ = arguments.resellAmounts, !isOwn, !self.isVisualGramGift, VisualGramLocalAppearance.shared.appearance(accountId: context.account.peerId).stars == nil {\n')

    buy = root / 'submodules/TelegramUI/Components/Gifts/GiftViewScreen/Sources/GiftViewBuyGift.swift'
    replace(buy, ') {\n    let presentationData = context.sharedContext.currentPresentationData.with { $0 }\n', ') {\n    if visualGramBuyLocalGift(context: context, recipientPeerId: recipientPeerId, gift: uniqueGift, getController: getController, completion: completion) { return }\n    let presentationData = context.sharedContext.currentPresentationData.with { $0 }\n')
    with buy.open('a', encoding='utf-8') as f:
        f.write(BUY_HELPER)

    bubble = root / 'submodules/TelegramUI/Components/Chat/ChatMessageGiftBubbleContentNode/Sources/ChatMessageGiftBubbleContentNode.swift'
    replace(bubble, 'authorName = item.message.author.flatMap { EnginePeer($0) }?.compactDisplayTitle ?? ""', 'authorName = (item.message.id.namespace == Int32.max - 42 && !item.message.flags.contains(.Incoming)) ? (item.associatedData.accountPeer?.compactDisplayTitle ?? "") : (item.message.author.flatMap { EnginePeer($0) }?.compactDisplayTitle ?? "")', expected=3)

    for relative in ['submodules/TelegramUI/Components/Gifts/GiftStoreScreen/Sources/BalanceComponent.swift', 'submodules/TelegramUI/Components/Stars/StarsBalanceOverlayComponent/Sources/StarsBalanceOverlayComponent.swift']:
        balance = root / relative
        text = balance.read_text(encoding='utf-8')
        text = text.replace('tonContext.state\n', 'tonContext.state,\n' + (' ' * (28 if 'Overlay' in relative else 24)) + 'VisualGramLocalAppearance.shared.changes\n')
        text = text.replace('starsState, tonState in', 'starsState, tonState, _ in')
        text = text.replace('self.starsBalance = starsState?.balance.value ?? 0', 'let appearance = VisualGramLocalAppearance.shared.appearance(accountId: component.context.account.peerId)\n' + (' ' * (28 if 'Overlay' in relative else 24)) + 'self.starsBalance = (appearance.enabled ? appearance.stars : nil) ?? starsState?.balance.value ?? 0')
        text = text.replace('presentationStringsFormattedNumber(Int32(self.starsBalance), presentationData.dateTimeFormat.groupingSeparator)', 'formatStarsAmountText(StarsAmount(value: self.starsBalance, nanos: 0), dateTimeFormat: presentationData.dateTimeFormat)')
        text = text.replace('presentationStringsFormattedNumber(Int32(clamping: self.starsBalance), presentationData.dateTimeFormat.groupingSeparator)', 'formatStarsAmountText(StarsAmount(value: self.starsBalance, nanos: 0), dateTimeFormat: presentationData.dateTimeFormat)')
        balance.write_text(text, encoding='utf-8')
    market = root / 'submodules/TelegramUI/Components/Gifts/GiftStoreScreen/Sources/GiftStoreScreen.swift'
    replace(market, '                let starsBalance = starsState?.balance ?? .zero\n', '                let appearance = VisualGramLocalAppearance.shared.appearance(accountId: component.context.account.peerId)\n                let starsBalance = (appearance.enabled ? appearance.stars : nil).map { StarsAmount(value: $0, nanos: 0) } ?? starsState?.balance ?? .zero\n')


BUY_HELPER = r'''

// Returns false only for the unchanged real purchase flow.
@discardableResult
func visualGramBuyLocalGift(context: AccountContext, recipientPeerId: EnginePeer.Id, gift: StarGift.UniqueGift, getController: @escaping () -> ViewController?, completion: @escaping () -> Void) -> Bool {
    let store = VisualGramLocalAppearance.shared
    let appearance = store.appearance(accountId: context.account.peerId)
    let requireListing = store.localReference(slug: gift.slug) != nil
    guard requireListing || (appearance.enabled && appearance.stars != nil) else { return false }
    guard let controller = getController() else { return true }
    let presentationData = context.sharedContext.currentPresentationData.with { $0 }
    let showError: (String) -> Void = { text in
        getController()?.present(textAlertController(context: context, title: "Локальная покупка", text: text, actions: [TextAlertAction(type: .defaultAction, title: presentationData.strings.Common_OK, action: {})]), in: .window(.root))
    }
    guard let price = gift.resellAmounts?.first(where: { $0.currency == .stars })?.amount.value, price > 0 else {
        showError("Этот подарок не выставлен за локальные звёзды.")
        return true
    }
    controller.present(textAlertController(context: context, title: "Купить локально", text: "\(gift.title) #\(gift.number)\nЦена: \(price) ★\nПокупка изменит только локальные подарки и баланс в этом клиенте.", actions: [
        TextAlertAction(type: .genericAction, title: presentationData.strings.Common_Cancel, action: {}),
        TextAlertAction(type: .defaultAction, title: "Купить за \(price) ★", action: {
            switch store.buyLocalGift(accountId: context.account.peerId, recipientPeerId: recipientPeerId, gift: gift, price: price, requireListing: requireListing, now: Int32(clamping: Int64(Date().timeIntervalSince1970))) {
            case .success: completion()
            case .insufficientBalance: showError("Недостаточно локальных звёзд.")
            case .priceChanged: showError("Цена изменилась. Открой подарок снова.")
            case .unavailable: showError("Подарок уже передан, куплен или принадлежит тебе.")
            case .invalid: showError("Настрой локальный баланс звёзд в Настройки → VisualGram.")
            }
        })
    ]), in: .window(.root))
    return true
}
'''
