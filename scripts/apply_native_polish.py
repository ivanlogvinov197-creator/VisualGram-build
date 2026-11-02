"""Post-1031 regression fixes; read-only collection metadata, local UI boundaries."""
from prepare_native import replace


def apply_polish(root, project):
    ui = root / 'submodules/TelegramUI/Components'
    core = root / 'submodules/TelegramCore/Sources/TelegramEngine/Payments/StarGifts.swift'
    with core.open('a', encoding='utf-8') as output:
        output.write(COLLECTION_SAMPLE)
    # Legacy locally upgraded gifts used a UUID that cannot be resolved by Telegram.
    text = core.read_text(encoding='utf-8')
    text = text.replace('self.visualGramMetadata.add((_internal_getUniqueStarGift(account: account, slug: gift.slug) |> deliverOnMainQueue).start(next: { fresh in\n                    VisualGramLocalAppearance.shared.updateLocalCraftMetadata', '''let metadata: Signal<StarGift.UniqueGift?, NoError>
                if gift.id < 0 && UUID(uuidString: String(gift.slug.dropFirst(5))) != nil {
                    metadata = visualGramGiftCollectionSample(account: account, giftId: gift.giftId)
                } else {
                    metadata = _internal_getUniqueStarGift(account: account, slug: gift.slug) |> map { Optional($0) } |> `catch` { _ in .single(nil) }
                }
                self.visualGramMetadata.add((metadata |> deliverOnMainQueue).start(next: { fresh in
                    guard let fresh else { return }
                    VisualGramLocalAppearance.shared.updateLocalCraftMetadata''', 1)
    core.write_text(text, encoding='utf-8')
    view = ui / 'Gifts/GiftViewScreen/Sources/GiftViewScreen.swift'
    replace(view, '        private let visualGramMetadata = MetaDisposable()\n', '        private let visualGramMetadata = MetaDisposable()\n        private var visualGramUpgradeTemplate: StarGift.UniqueGift?\n')
    replace(view, 'self.visualGramMetadata.set((context.engine.payments.getUniqueStarGift(slug: gift.slug) |> deliverOnMainQueue).start(next: { [weak self] fresh in\n                    guard let self else { return }', '''let metadata: Signal<StarGift.UniqueGift?, NoError>
                if gift.id < 0 && UUID(uuidString: String(gift.slug.dropFirst(5))) != nil {
                    metadata = visualGramGiftCollectionSample(account: context.account, giftId: gift.giftId)
                } else {
                    metadata = context.engine.payments.getUniqueStarGift(slug: gift.slug) |> map { Optional($0) } |> `catch` { _ in .single(nil) }
                }
                self.visualGramMetadata.set((metadata |> deliverOnMainQueue).start(next: { [weak self] fresh in
                    guard let self, let fresh else { return }''')
    replace(view, '            if self.isVisualGramGift, let arguments = self.subject.arguments, case .generic = arguments.gift {\n', '''            if self.isVisualGramGift, let arguments = self.subject.arguments, case let .generic(generic) = arguments.gift {
                guard !self.inProgress, self.visualGramCanManage else { return }
                if self.visualGramUpgradeTemplate == nil {
                    self.inProgress = true; self.updated()
                    self.visualGramMetadata.set((visualGramGiftCollectionSample(account: self.context.account, giftId: generic.id) |> deliverOnMainQueue).start(next: { [weak self] template in
                        guard let self else { return }
                        self.inProgress = false
                        guard let template else {
                            self.updated()
                            self.showAttributeInfo(tag: self.statusTag, text: "Не удалось загрузить коллекцию. Попробуй ещё раз.")
                            return
                        }
                        self.visualGramUpgradeTemplate = template
                        self.commitUpgrade()
                    }))
                    return
                }
''')
    replace(view, 'preview: preview, keepOriginalInfo: self.keepOriginalInfo)', 'preview: preview, keepOriginalInfo: self.keepOriginalInfo, template: self.visualGramUpgradeTemplate)')
    # Keep the owner's original menu; foreign local gifts expose read-only actions.
    text = view.read_text(encoding='utf-8')
    start = text.index('        func openMore() {')
    end = text.index('        func dismiss(animated:', start)
    part = text[start:end]
    part = part.replace('if self.canDeleteGift {', 'if self.canDeleteGift && (!self.isVisualGramGift || self.visualGramCanManage) {')
    part = part.replace('if let reference = arguments.reference, case .unique', 'if (!self.isVisualGramGift || self.visualGramCanManage), let reference = arguments.reference, case .unique')
    part = part.replace('if arguments.reference != nil || gift.owner?.peerId == self.context.account.peerId {', 'if (!self.isVisualGramGift || self.visualGramCanManage) && (arguments.reference != nil || gift.owner?.peerId == self.context.account.peerId) {')
    part = part.replace('if let displayed = self.onchainProfileDisplayState(gift) {', 'if (!self.isVisualGramGift || self.visualGramCanManage), let displayed = self.onchainProfileDisplayState(gift) {')
    part = part.replace('if let _ = arguments.canCraftDate {', 'if (!self.isVisualGramGift || self.visualGramCanManage), let _ = arguments.canCraftDate {')
    part = part.replace('if arguments.transferStars != nil || self.isMyWalletGift(gift) {', 'if (!self.isVisualGramGift || self.visualGramCanManage) && (arguments.transferStars != nil || self.isMyWalletGift(gift)) {')
    text = text[:start] + part + text[end:]
    # Show an explicitly written caption without a generated receipt sentence.
    start = text.index('                            case let .originalInfo(senderPeerId, recipientPeerId, date, text, entities):')
    end = text.index('                                hasOriginalInfo = true\n', start) + len('                                hasOriginalInfo = true\n')
    part = text[start:end]
    marker = '                                let senderName = '
    position = part.index(marker)
    part = part[:position] + '''                                if state.isVisualGramGift {
                                    guard let text, !text.isEmpty else { continue }
                                    value = stringWithAppliedEntities(text, entities: entities ?? [], baseColor: tableTextColor, linkColor: tableLinkColor, baseFont: tableFont, linkFont: tableFont, boldFont: tableBoldFont, italicFont: tableItalicFont, boldItalicFont: tableBoldItalicFont, fixedFont: tableMonospaceFont, blockQuoteFont: tableFont, message: nil)
                                    rarity = nil; tag = nil; hasOriginalInfo = true
                                } else {
''' + part[position:] + '                                }\n'
    text = text[:start] + part + text[end:]
    view.write_text(text, encoding='utf-8')
    setup = ui / 'Gifts/GiftSetupScreen/Sources/GiftSetupScreen.swift'
    text = setup.read_text(encoding='utf-8')
    start = text.index('        private func proceedWithVisualGramGift(')
    end = text.index('        private func proceedWithStarGift()', start)
    part = text[start:end]
    part = part.replace('let commit: (StarGiftUpgradePreview?) -> Void = { [weak self, weak controller] preview in', 'let commit: (StarGiftUpgradePreview?, StarGift.UniqueGift?) -> Void = { [weak self, weak controller] preview, template in')
    part = part.replace('now: Int32(clamping: Int64(Date().timeIntervalSince1970)))', 'now: Int32(clamping: Int64(Date().timeIntervalSince1970)), upgradeTemplate: template)')
    part = part.replace('let _ = (context.engine.payments.starGiftUpgradePreview(giftId: gift.id) |> take(1) |> deliverOnMainQueue).start(next: commit)', '''let _ = (combineLatest(context.engine.payments.starGiftUpgradePreview(giftId: gift.id), visualGramGiftCollectionSample(account: context.account, giftId: gift.id)) |> take(1) |> deliverOnMainQueue).start(next: { preview, template in
                    guard template != nil else { commit(nil, nil); return }
                    commit(preview, template)
                })''')
    part = part.replace('} else { commit(nil) }', '} else { commit(nil, nil) }')
    setup.write_text(text[:start] + part + text[end:], encoding='utf-8')


COLLECTION_SAMPLE = r'''

// A local upgrade uses a real collection sample for its number, link and craft
// metadata. This only reads the resale catalogue; it never purchases a lot.
public func visualGramGiftCollectionSample(account: Account, giftId: Int64) -> Signal<StarGift.UniqueGift?, NoError> {
    return Signal { subscriber in
        let catalog = ResaleGiftsContext(account: account, giftId: giftId, forCrafting: false)
        let disposable = (catalog.state |> filter { state in
            if case .ready = state.dataState { return true }; return false
        } |> take(1) |> mapToSignal { state -> Signal<StarGift.UniqueGift?, NoError> in
            let owned = Set(VisualGramLocalAppearance.shared.appearance(accountId: account.peerId).gifts.compactMap { local -> String? in
                if local.direction == .received, local.isHistoryOnly != true, case let .unique(gift) = local.gift { return gift.slug }; return nil
            })
            let candidates = state.gifts.compactMap { item -> StarGift.UniqueGift? in
                guard case let .unique(gift) = item, gift.id > 0, gift.giftId == giftId,
                      !owned.contains(gift.slug), !gift.flags.contains(.isBurned),
                      !gift.attributes.contains(where: { if case let .model(_, _, _, crafted) = $0 { return crafted }; return false }) else { return nil }
                return gift
            }
            guard let candidate = candidates.randomElement() else { return .single(nil) }
            // Fetch the complete collectible, including craft eligibility that
            // need not be present in an ordinary resale-list response.
            return _internal_getUniqueStarGift(account: account, slug: candidate.slug)
            |> map { Optional($0) } |> `catch` { _ in .single(nil) }
        }).start(next: { gift in
            subscriber.putNext(gift); subscriber.putCompletion()
        })
        return ActionDisposable { disposable.dispose(); withExtendedLifetime(catalog) {} }
    }
}
'''
