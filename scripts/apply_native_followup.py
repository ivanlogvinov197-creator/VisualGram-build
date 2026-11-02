"""Agreed post-1029 menu and original gift purchase/craft entry paths."""
import shutil
from prepare_native import replace


def apply_followup(root, project):
    ui = root / 'submodules/TelegramUI/Components'
    peer = ui / 'PeerInfo/PeerInfoScreen/Sources'
    shutil.copyfile(project / 'native/VisualGramMenuForms.swift', peer / 'VisualGramMenuForms.swift')
    view = ui / 'Gifts/GiftViewScreen/Sources/GiftViewScreen.swift'
    text = view.read_text(encoding='utf-8')
    start = text.index('        func craftGift() {')
    end = text.index('        func depositGift(', start)
    part = text[start:end]
    assert part.count('            guard !self.isVisualGramGift else { return }\n') == 1
    part = part.replace('            guard !self.isVisualGramGift else { return }\n', '', 1)
    text = text[:start] + part + text[end:]
    text = text.replace('if uniqueGift.resellForTonOnly && !state.visualGramCatalogPurchase {', 'if uniqueGift.resellForTonOnly {')
    view.write_text(text, encoding='utf-8')
    options = ui / 'Gifts/GiftOptionsScreen/Sources/GiftOptionsScreen.swift'
    replace(options, '        fileprivate var starGifts: [StarGift]?\n', '        fileprivate var starGifts: [StarGift]?\n        fileprivate var visualGramAllStarGifts: [StarGift]?\n')
    replace(options, '                var filteredStarGifts = starGifts\n', '                self.visualGramAllStarGifts = starGifts\n                var filteredStarGifts = starGifts\n')
    replace(options, '                } else if let state = self.state, let allGifts = state.starGifts {\n', '                } else if let state = self.state, let allGifts = ((self.environment?.controller() as? GiftOptionsScreen)?.visualGramGiftSelected != nil ? state.visualGramAllStarGifts : state.starGifts) {\n')
    replace(options, 'disallowedGifts == .All, let controller = controller(), !self.dismissed {', 'disallowedGifts == .All, let controller = controller(), (controller as? GiftOptionsScreen)?.visualGramGiftSelected == nil, !self.dismissed {')
    buy = ui / 'Gifts/GiftViewScreen/Sources/GiftViewBuyGift.swift'
    text = buy.read_text(encoding='utf-8')
    start = text.index('// Returns false only for the unchanged real purchase flow.')
    text = text[:start] + BUY_HELPER
    text = text.replace('    completion: @escaping () -> Void\n) {', '    completion: @escaping () -> Void,\n    visualGramLocal: Bool = false\n) {', 1)
    text = text.replace('    if visualGramBuyLocalGift(context:', '    if visualGramLocal && buyGift == nil { return }\n    if !visualGramLocal && visualGramBuyLocalGift(context:', 1)
    text = text.replace('if finalPrice.currency == .stars, let starsContext', 'if !visualGramLocal, finalPrice.currency == .stars, let starsContext')
    text = text.replace('} else if finalPrice.currency == .ton, let tonState', '} else if !visualGramLocal, finalPrice.currency == .ton, let tonState')
    text = text.replace('completion: completion\n', 'completion: completion, visualGramLocal: visualGramLocal\n')
    text = text.replace('updateIsBalanceVisible(true)\n                    }\n                )', 'updateIsBalanceVisible(true)\n                    },\n                    starsOnly: visualGramLocal && uniqueGift.resellAmounts?.contains(where: { $0.currency == .ton && $0.amount.value > 0 }) != true\n                )', 1)
    buy.write_text(text, encoding='utf-8')


BUY_HELPER = r'''
// Native message/privacy and currency-confirmation screens; local payment boundary.
@discardableResult
func visualGramBuyLocalGift(context: AccountContext, recipientPeerId: EnginePeer.Id, gift: StarGift.UniqueGift, getController: @escaping () -> ViewController?, completion: @escaping () -> Void) -> Bool {
    let store = VisualGramLocalAppearance.shared
    let value = store.appearance(accountId: context.account.peerId)
    let requireListing = store.localReference(slug: gift.slug) != nil
    guard requireListing || (value.enabled && (value.stars != nil || value.grams != nil)) else { return false }
    guard let controller = getController() else { return true }
    let data = context.currentAppConfiguration.with { $0 }.data
    var rate: Decimal?
    if let ton = data?["ton_usd_rate"] as? Double, let stars = data?["stars_usd_withdraw_rate_x1000"] as? Double, ton.isFinite, stars.isFinite, ton > 0, stars > 0 {
        rate = Decimal(ton) / (Decimal(stars) / 1000 / 100)
    }
    let quotedGift = store.giftForLocalPurchase(accountId: context.account.peerId, gift: gift, starsPerGram: rate)
    let showError: (String) -> Void = { message in
        let presentationData = context.sharedContext.currentPresentationData.with { $0 }
        getController()?.present(textAlertController(context: context, title: nil, text: message, actions: [TextAlertAction(type: .defaultAction, title: presentationData.strings.Common_OK, action: {})]), in: .window(.root))
    }
    guard !gift.resellForTonOnly || quotedGift.resellAmounts?.contains(where: { $0.currency == .ton && $0.amount.value > 0 }) == true else {
        showError("Не удалось загрузить цену GRAM. Проверь подключение и открой подарок ещё раз.")
        return true
    }
    buyStarGiftImpl(context: context, recipientPeerId: recipientPeerId, uniqueGift: quotedGift, showAttributes: true, starsTopUpOptions: .single([]), buyGift: { _, recipient, price, hideName, text, entities in
        guard let price else { return .fail(.generic) }
        let now = Int32(clamping: Int64(Date().timeIntervalSince1970))
        let result: VisualGramGiftPurchaseResult
        if price.currency == .ton {
            result = store.buyLocalGiftWithGrams(accountId: context.account.peerId, recipientPeerId: recipient, gift: gift, price: price.amount.value, requireListing: requireListing, now: now, starsPerGram: rate, text: text ?? "", nameHidden: hideName, entities: entities)
        } else {
            result = store.buyLocalGift(accountId: context.account.peerId, recipientPeerId: recipient, gift: gift, price: price.amount.value, requireListing: requireListing, now: now, text: text ?? "", nameHidden: hideName, entities: entities)
        }
        switch result {
        case .success: return .complete()
        case .insufficientBalance: showError(price.currency == .ton ? "Недостаточно GRAM" : "Недостаточно звёзд")
        case .priceChanged: showError("Цена подарка изменилась. Открой предложение ещё раз.")
        case .unavailable: showError("Подарок больше недоступен.")
        case .invalid: showError("Настрой баланс выбранной валюты.")
        }
        return .fail(.serverProvided(""))
    }, getController: getController, updateProgress: { _ in }, updateIsBalanceVisible: { _ in }, completion: {
        visualGramFinishGift(context: context, peerId: recipientPeerId, controller: controller, completion: completion)
    }, visualGramLocal: true)
    return true
}
'''
