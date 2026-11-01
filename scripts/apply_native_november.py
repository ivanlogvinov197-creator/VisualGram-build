"""Local-only extensions for the pinned Telegram 13.1.2 native screens."""
import shutil
from prepare_native import replace


def apply_november(root, project):
    core = root / 'submodules/TelegramCore/Sources'
    ui = root / 'submodules/TelegramUI/Components'
    for name in ['VisualGramWallet.swift', 'VisualGramGiftCrafting.swift']:
        shutil.copyfile(project / 'native' / name, core / name)
    peer_module = ui / 'PeerInfo/PeerInfoScreen'
    shutil.copyfile(project / 'native/VisualGramGiftGridController.swift', peer_module / 'Sources/VisualGramGiftGridController.swift')
    build = peer_module / 'BUILD'
    build_text = build.read_text(encoding='utf-8')
    for dependency in ['//submodules/TelegramUI/Components/Gifts/GiftItemComponent', '//submodules/TelegramUI/Components/Settings/BusinessHoursSetupScreen', '//submodules/TelegramUI/Components/Settings/BusinessLocationSetupScreen']:
        if '"' + dependency + '"' not in build_text:
            build_text = build_text.replace('    deps = [\n', '    deps = [\n        "' + dependency + '",\n', 1)
    build.write_text(build_text, encoding='utf-8')

    gifts = core / 'TelegramEngine/Payments/StarGifts.swift'
    text = gifts.read_text(encoding='utf-8')
    start = text.index('public final class CraftGiftsContext {')
    end = text.index('public enum CraftStarGiftError', start)
    part = text[start:end]
    def change(old, new):
        nonlocal part
        if part.count(old) != 1: raise ValueError('Craft context layout changed: ' + old[:65])
        part = part.replace(old, new, 1)
    change('    public let giftId: Int64\n', '    public let giftId: Int64\n    public let visualGramAccountId: EnginePeer.Id\n    public let visualGramLocal: Bool\n    private let visualGramAccount: Account\n')
    change('        limit: Int32 = 36\n', '        limit: Int32 = 36,\n        visualGramLocal: Bool = false\n')
    change('        self.giftId = giftId\n', '        self.giftId = giftId\n        self.visualGramAccountId = account.peerId\n        self.visualGramAccount = account\n        self.visualGramLocal = visualGramLocal\n')
    # Restrict to the state property; craft() also contains a Signal constructor.
    marker = '    public var state: Signal<CraftGiftsContext.State, NoError> {\n'
    change(marker, marker + '''        if self.visualGramLocal {
            return VisualGramLocalAppearance.shared.changes |> map { _ in
                let gifts = VisualGramLocalAppearance.shared.craftableLocalGifts(accountId: self.visualGramAccountId, giftId: self.giftId, now: Int32(clamping: Int64(Date().timeIntervalSince1970)))
                return State(gifts: gifts.map { $0.profileGift(accountId: self.visualGramAccountId, sender: nil) }, count: Int32(gifts.count), dataState: .ready(canLoadMore: false, nextOffset: nil))
            }
        }
''')
    change('    public func craft(references: [StarGiftReference]) -> Signal<ProfileGiftsContext.State.StarGift, CraftStarGiftError> {\n', '''    public func craft(references: [StarGiftReference], visualGramAttributePermilles: [[Int32]]? = nil) -> Signal<ProfileGiftsContext.State.StarGift, CraftStarGiftError> {
        if self.visualGramLocal || references.contains(where: { VisualGramLocalAppearance.isLocalReference($0) }) {
            guard self.visualGramLocal, references.allSatisfy({ VisualGramLocalAppearance.isLocalReference($0) }), let probabilities = visualGramAttributePermilles else { return .fail(.unavailable) }
            return _internal_getStarGiftUpgradeAttributes(account: self.visualGramAccount, giftId: self.giftId)
            |> take(1) |> castError(CraftStarGiftError.self)
            |> mapToSignal { attributes in
                guard let attributes else { return .fail(.unavailable) }
                switch VisualGramLocalAppearance.shared.craftLocalGifts(accountId: self.visualGramAccountId, references: references, attributes: attributes, attributePermilles: probabilities, now: Int32(clamping: Int64(Date().timeIntervalSince1970)))) {
                case let .success(gift): return .single(gift.profileGift(accountId: self.visualGramAccountId, sender: nil))
                case let .failure(error): return .fail(error)
                }
            }
        }
'''.replace('timeIntervalSince1970))))', 'timeIntervalSince1970)))'))
    for signature in ['loadMore()', 'reload()', 'removeGifts(references: [StarGiftReference])']:
        change('    public func ' + signature + ' {\n', '    public func ' + signature + ' {\n        if self.visualGramLocal { return }\n')
    gifts.write_text(text[:start] + part + text[end:], encoding='utf-8')
    craft = ui / 'Gifts/GiftCraftScreen/Sources/GiftCraftScreen.swift'
    replace(craft, 'let craftContext = CraftGiftsContext(account: context.account, giftId: gift.giftId)', 'let local = VisualGramLocalAppearance.shared.localReference(slug: gift.slug).map { VisualGramLocalAppearance.shared.canManageLocalGift(accountId: context.account.peerId, reference: $0) } ?? false\n        let craftContext = CraftGiftsContext(account: context.account, giftId: gift.giftId, visualGramLocal: local)')
    replace(craft, 'craftContext.craft(references: references)', 'craftContext.craft(references: references, visualGramAttributePermilles: GiftCraftConfiguration.with(appConfiguration: component.context.currentAppConfiguration.with { $0 }).craftAttributePermilles)')
    # Local consumption and insertion are already committed atomically by the
    # local store. Native optimistic cache updates would delete its history and
    # leak the synthetic result into server-only presentation after disabling it.
    replace(craft, '                                controller.profileGiftsContext?.removeStarGifts(references: references)\n', '                                if !component.craftContext.visualGramLocal { controller.profileGiftsContext?.removeStarGifts(references: references) }\n')
    replace(craft, '                                        controller.profileGiftsContext?.insertStarGifts(gifts: [gift], afterPinned: true)\n', '                                        if !component.craftContext.visualGramLocal { controller.profileGiftsContext?.insertStarGifts(gifts: [gift], afterPinned: true) }\n')
    view = ui / 'Gifts/GiftViewScreen/Sources/GiftViewScreen.swift'
    replace(view, '        func craftGift() {\n', '        func craftGift() {\n            if VisualGramLocalAppearance.isLocalReference(self.subject.arguments?.reference), !VisualGramLocalAppearance.shared.canManageLocalGift(accountId: self.context.account.peerId, reference: self.subject.arguments?.reference) { return }\n')

    # Build a display copy of cached profile data. No Postbox or account update.
    peer = ui / 'PeerInfo/PeerInfoScreen/Sources/PeerInfoScreen.swift'
    replace(peer, '                return data\n            },\n            self.forceIsContactPromise.get(),', '''                if appearance.enabled, var cached = data.cachedData as? CachedUserData {
                    if appearance.overridesBusinessHours == true { cached = cached.withUpdatedBusinessHours(appearance.businessHours) }
                    if appearance.overridesBusinessLocation == true { cached = cached.withUpdatedBusinessLocation(appearance.businessLocation) }
                    cached = cached.withUpdatedWalletCard(VisualGramLocalAppearance.shared.displayWalletCard(accountId: context.account.peerId, peerId: peerId, server: cached.walletCard))
                    data.cachedData = cached
                }
                return data
            },
            self.forceIsContactPromise.get(),''')
    replace(peer, 'card: (self.data?.cachedData as? CachedUserData)?.walletCard, sourceView:', 'card: (self.data?.serverCachedData as? CachedUserData)?.walletCard, sourceView:')
    wallet = ui / 'Wallet/PeerWalletScreen/Sources/PeerWalletScreen.swift'
    replace(wallet, '        private(set) var card: WalletCard?\n', '        private(set) var card: WalletCard?\n        private var serverCard: WalletCard?\n')
    replace(wallet, '            self.updateCard(card, context: context)\n', '''            self.updateCard(card, context: context)
            self.disposables.add((VisualGramLocalAppearance.shared.changes |> deliverOnMainQueue).start(next: { [weak self] _ in
                guard let self else { return }
                self.updateCard(self.serverCard, context: context)
                self.updated(transition: .immediate)
            }))
''')
    replace(wallet, '        private func updateCard(_ card: WalletCard?, context: AccountContext) {\n', '''        private func updateCard(_ card: WalletCard?, context: AccountContext) {
            self.serverCard = card
            let card = VisualGramLocalAppearance.shared.displayWalletCard(accountId: context.account.peerId, peerId: self.peer.id, server: card)
''')
    # A local balance must never make a real send-money action look funded.
    replace(peer, '                guard let walletContext = self.context.walletContext else { return }\n', '''                let localWallet = VisualGramLocalAppearance.shared.appearance(accountId: self.context.account.peerId, targetPeerId: peer.id)
                if localWallet.enabled && localWallet.grams != nil { return }
                guard let walletContext = self.context.walletContext else { return }
''')
    # Standalone native business editors with a local save target.
    for name, value in [('BusinessHours', 'businessHours'), ('BusinessLocation', 'businessLocation')]:
        path = ui / f'Settings/{name}SetupScreen/Sources/{name}SetupScreen.swift'
        text = path.read_text(encoding='utf-8')
        text = text.replace('    let context: AccountContext\n', '    let context: AccountContext\n    let visualGramTarget: EnginePeer.Id?\n', 1)
        old = f'        completion: @escaping (Telegram{name}?) -> Void\n'
        if text.count(old) != (1 if name == 'BusinessHours' else 2): raise ValueError('Business editor initializer changed')
        text = text.replace(old, f'        completion: @escaping (Telegram{name}?) -> Void,\n        visualGramTarget: EnginePeer.Id? = nil\n')
        # Hours' public initializer is on one line.
        if name == 'BusinessHours':
            old = 'public init(context: AccountContext, initialValue: TelegramBusinessHours?, completion: @escaping (TelegramBusinessHours?) -> Void) {'
            if text.count(old) != 1: raise ValueError('Business hours screen initializer changed')
            text = text.replace(old, old.replace(') {', ', visualGramTarget: EnginePeer.Id? = nil) {'))
        text = text.replace('        self.completion = completion\n', '        self.completion = completion\n        self.visualGramTarget = visualGramTarget\n', 1)
        text = text.replace('            completion: completion\n', '            completion: completion,\n            visualGramTarget: visualGramTarget\n', 1)
        import re
        pattern = rf'(?m)^(\s*)let _ = component.context.engine.accountData.updateAccount{name}\({value}: ([^\n]+)\).startStandalone\(\)$'
        def save(match):
            space, expression = match.group(1), match.group(2)
            return f'''{space}if let target = component.visualGramTarget {{
{space}    VisualGramLocalAppearance.shared.update(accountId: component.context.account.peerId, targetPeerId: target) {{ $0.enabled = true; $0.overrides{name} = true; $0.{value} = {expression} }}
{space}}} else {{
{space}    {match.group(0).strip()}
{space}}}'''
        text, count = re.subn(pattern, save, text)
        if count != (2 if name == 'BusinessHours' else 1): raise ValueError('Business editor save path changed')
        path.write_text(text, encoding='utf-8')

    style = ui / 'Settings/PeerNameColorScreen/Sources/UserApperanceScreen.swift'
    text = style.read_text(encoding='utf-8')
    text = text.replace('    let context: AccountContext\n', '    let context: AccountContext\n    let visualGramTarget: EnginePeer.Id?\n', 1)
    text = text.replace('        context: AccountContext\n    ) {\n        self.context = context\n', '        context: AccountContext,\n        visualGramTarget: EnginePeer.Id? = nil\n    ) {\n        self.context = context\n        self.visualGramTarget = visualGramTarget\n', 1)
    text = text.replace('        focusOnItemTag: UserAppearanceEntryTag? = nil\n', '        focusOnItemTag: UserAppearanceEntryTag? = nil,\n        visualGramTarget: EnginePeer.Id? = nil\n', 1)
    text = text.replace('component: UserAppearanceScreenComponent(\n            context: context\n', 'component: UserAppearanceScreenComponent(\n            context: context,\n            visualGramTarget: visualGramTarget\n', 1)
    text = text.replace('static func get(context: AccountContext) -> Signal<ContentsData, NoError>', 'static func get(context: AccountContext, visualGramTarget: EnginePeer.Id?) -> Signal<ContentsData, NoError>', 1)
    text = text.replace('Item.Peer.Peer(id: context.account.peerId)', 'Item.Peer.Peer(id: visualGramTarget ?? context.account.peerId)', 1)
    text = text.replace('                context.engine.payments.cachedStarGifts()\n', '                context.engine.payments.cachedStarGifts(),\n                VisualGramLocalAppearance.shared.changes\n', 1)
    text = text.replace('map { peer, view, starGifts -> ContentsData in', 'map { peer, view, starGifts, _ -> ContentsData in', 1)
    text = text.replace('                return ContentsData(\n                    peer: peer,', '''                if let target = visualGramTarget {
                    if target != context.account.peerId { gifts = [] }
                    let value = VisualGramLocalAppearance.shared.appearance(accountId: context.account.peerId, targetPeerId: target)
                    let local = value.gifts.compactMap { item -> StarGift.UniqueGift? in
                        guard item.direction == .received, item.isHistoryOnly != true, case let .unique(gift) = item.gift else { return nil }
                        return gift
                    }
                    let ids = Set(local.map { $0.slug })
                    gifts = local + gifts.filter { !ids.contains($0.slug) }
                }
                return ContentsData(
                    peer: visualGramTarget == nil ? peer : VisualGramLocalAppearance.shared.displayPeer(peer, accountId: context.account.peerId),''', 1)
    text = text.replace('ContentsData.get(context: component.context)', 'ContentsData.get(context: component.context, visualGramTarget: component.visualGramTarget)', 1)
    old = '            } else if !component.context.isPremium {'
    if text.count(old) != 1: raise ValueError('Appearance premium check changed')
    text = text.replace(old, '            } else if component.visualGramTarget == nil && !component.context.isPremium {', 1)
    # Stop before any purchase / server profile mutation for this editor instance.
    marker = '            if self.selectedProfileGift != nil || self.selectedNameGift != nil {\n'
    if text.count(marker) != 1: raise ValueError('Appearance save path changed')
    text = text.replace(marker, '''            if let target = component.visualGramTarget {
                VisualGramLocalAppearance.shared.update(accountId: component.context.account.peerId, targetPeerId: target) {
                    $0.enabled = true; $0.premium = true; $0.overridesProfileStyle = true
                    $0.profileColor = resolvedState.profileColor?.rawValue
                    $0.profileBackgroundEmojiId = resolvedState.backgroundFileId
                    $0.nameColor = VisualGramNameColor(resolvedState.nameColor)
                    $0.nameBackgroundEmojiId = resolvedState.replyFileId
                    $0.overridesEmojiStatus = true; $0.emojiStatus = resolvedState.emojiStatus
                }
                environment.controller()?.dismiss()
                return
            }
''' + marker, 1)
    style.write_text(text, encoding='utf-8')

    for relative in ['Gifts/GiftStoreScreen/Sources/BalanceComponent.swift', 'Stars/StarsBalanceOverlayComponent/Sources/StarsBalanceOverlayComponent.swift']:
        balance = ui / relative
        replace(balance, '            if localBalance.enabled, let stars = localBalance.stars { self.starsBalance = stars }\n' if relative.startswith('Gifts/') else '            if component.peerId == component.context.account.peerId && localBalance.enabled, let stars = localBalance.stars { self.starsBalance = stars }\n',
                ('            if localBalance.enabled, let stars = localBalance.stars { self.starsBalance = stars }\n            if localBalance.enabled, let grams = localBalance.grams { self.tonBalance = grams }\n' if relative.startswith('Gifts/') else '            if component.peerId == component.context.account.peerId && localBalance.enabled, let stars = localBalance.stars { self.starsBalance = stars }\n            if component.peerId == component.context.account.peerId && localBalance.enabled, let grams = localBalance.grams { self.tonBalance = grams }\n'))
        if relative.startswith('Gifts/'):
            replace(balance, '            if self.tonBalance > 0 {\n', '            if self.tonBalance > 0 || (localBalance.enabled && localBalance.grams != nil) {\n')

    screen = ui / 'Stars/StarsTransactionsScreen/Sources/StarsTransactionsScreen.swift'
    replace(screen, '            let appearance = VisualGramLocalAppearance.shared.appearance(accountId: component.context.account.peerId)\n', '            let appearance = VisualGramLocalAppearance.shared.appearance(accountId: component.context.account.peerId)\n            let showLocalGrams = component.starsContext.ton && component.starsContext.peerId == component.context.account.peerId && appearance.enabled && appearance.grams != nil\n')
    replace(screen, 'formattedBalance = formatTonAmountText(self.starsState?.balance.value ?? 0,', 'formattedBalance = formatTonAmountText((showLocalGrams ? appearance.grams : nil) ?? self.starsState?.balance.value ?? 0,')
    # Keep server balances intact; only this display component receives the local amount.
    replace(screen, '                            count: displayStarsBalance,\n', '                            count: showLocalGrams ? appearance.grams.map { StarsAmount(value: $0, nanos: 0) } ?? displayStarsBalance : displayStarsBalance,\n')
    replace(screen, 'value: self.revenueState?.balances.availableBalance ?? CurrencyAmount(amount: .zero, currency: .ton),', 'value: (showLocalGrams ? appearance.grams : nil).map { CurrencyAmount(amount: StarsAmount(value: $0, nanos: 0), currency: .ton) } ?? self.revenueState?.balances.availableBalance ?? CurrencyAmount(amount: .zero, currency: .ton),')
    replace(screen, 'value: self.revenueState?.balances.overallRevenue ?? CurrencyAmount(amount: .zero, currency: .ton),', 'value: (showLocalGrams ? appearance.gramHistory : nil).map { history in CurrencyAmount(amount: StarsAmount(value: history.filter { $0.amount > 0 }.reduce(Int64(0)) { sum, entry in let (next, overflow) = sum.addingReportingOverflow(entry.amount); return overflow ? Int64.max : next }, nanos: 0), currency: .ton) } ?? self.revenueState?.balances.overallRevenue ?? CurrencyAmount(amount: .zero, currency: .ton),')

    market = ui / 'Gifts/GiftStoreScreen/Sources/GiftStoreScreen.swift'
    replace(market, '            let tonBalance = tonContext.currentState?.balance.value ?? 0\n            if tonBalance == 0 {', '            let wallet = VisualGramLocalAppearance.shared.appearance(accountId: component.context.account.peerId)\n            let tonBalance = (wallet.enabled ? wallet.grams : nil) ?? tonContext.currentState?.balance.value ?? 0\n            if tonBalance == 0 && !(wallet.enabled && wallet.grams != nil) {')
    replace(market, '                let tonBalance = tonState?.balance.value ?? 0\n', '                let wallet = VisualGramLocalAppearance.shared.appearance(accountId: component.context.account.peerId)\n                let tonBalance = (wallet.enabled ? wallet.grams : nil) ?? tonState?.balance.value ?? 0\n')

    replace(market, 'guard let component = self.component, let starsContext = component.context.starsContext, let tonContext = component.context.tonContext, let controller = self.environment?.controller() else {', 'guard let component = self.component, let controller = self.environment?.controller() else { return }\n            let starsContext = component.context.starsContext ?? component.context.engine.payments.peerStarsContext()\n            let tonContext = component.context.tonContext ?? component.context.engine.payments.peerTonContext()\n            do {')
    replace(screen, '                            actionIsEnabled: true,\n', '                            actionIsEnabled: !showLocalGrams,\n')
