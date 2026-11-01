import Foundation

public extension VisualGramLocalAppearance {
    static let gramScale: Int64 = 1_000_000_000

    static func parseGrams(_ text: String) -> Int64? {
        let normalized = text.trimmingCharacters(in: .whitespacesAndNewlines).replacingOccurrences(of: ",", with: ".")
        guard normalized.range(of: "^[0-9]+(?:\\.[0-9]{1,9})?$", options: .regularExpression) != nil,
              let amount = Decimal(string: normalized, locale: Locale(identifier: "en_US_POSIX")) else { return nil }
        let nano = amount * Decimal(gramScale)
        guard nano >= 0, nano <= Decimal(Int64.max) else { return nil }
        return NSDecimalNumber(decimal: nano).int64Value
    }

    static func formatGrams(_ nano: Int64) -> String {
        NSDecimalNumber(decimal: Decimal(nano) / Decimal(gramScale)).stringValue
    }

    func localGramPrice(accountId: EnginePeer.Id, gift: StarGift.UniqueGift) -> Int64? {
        if let amount = gift.resellAmounts?.first(where: { $0.currency == .ton })?.amount.value, amount > 0 { return amount }
        let value = self.appearance(accountId: accountId)
        guard let price = gift.resellAmounts?.first(where: { $0.currency == .stars })?.amount.value,
              price > 0, let rate = value.gramStarsPerUnit, rate > 0 else { return nil }
        var raw = Decimal(price) * Decimal(Self.gramScale) / Decimal(rate)
        var rounded = Decimal()
        NSDecimalRound(&rounded, &raw, 0, .up)
        guard rounded > 0, rounded <= Decimal(Int64.max) else { return nil }
        return NSDecimalNumber(decimal: rounded).int64Value
    }

    func displayWalletCard(accountId: EnginePeer.Id, peerId: EnginePeer.Id, server: WalletCard?) -> WalletCard? {
        let value = self.appearance(accountId: accountId, targetPeerId: peerId)
        guard value.enabled, let grams = value.grams else { return server }
        let selected = (value.gramCardGiftIds ?? []).prefix(10).compactMap { id -> VisualGramGift? in
            value.gifts.first { $0.identifier == id && $0.direction == .received && $0.isHistoryOnly != true }
        }
        let stickers = selected.enumerated().compactMap { index, local -> WalletCard.Sticker? in
            guard case let .unique(gift) = local.displayGift(accountId: peerId) else { return nil }
            let nft = WalletNftItem(collectionAddress: nil, address: "visualgram:" + gift.slug, ownerAddress: "", index: String(gift.number), name: gift.title, description: nil, image: nil, imageSmall: nil, contentUrl: nil, lottie: nil, attributes: nil, extra: nil, gift: gift)
            return WalletCard.Sticker(coordinates: .init(x: 20.0 + Double(index % 4) * 20.0, y: 74.0 - Double(index / 4) * 24.0, width: 24.0, height: 40.0, rotation: 0.0, cornerRadius: nil), nft: nft)
        }
        var background: WalletNftItem?
        if let local = selected.first(where: { $0.identifier == value.gramCardBackgroundId }), case let .unique(gift) = local.gift {
            background = stickers.first(where: { $0.nft.address == "visualgram:" + gift.slug })?.nft
        }
        // Empty address keeps the native receive/QR action unavailable for a local card.
        return WalletCard(address: "", balance: grams, stickers: stickers, backgroundNft: background)
    }

    func giftForLocalPurchase(accountId: EnginePeer.Id, gift: StarGift.UniqueGift) -> StarGift.UniqueGift {
        var prices = gift.resellAmounts ?? []
        let value = self.appearance(accountId: accountId)
        if value.enabled, value.grams != nil, let price = self.localGramPrice(accountId: accountId, gift: gift), !prices.contains(where: { $0.currency == .ton }) {
            prices.append(CurrencyAmount(amount: StarsAmount(value: price, nanos: 0), currency: .ton))
        }
        return StarGift.UniqueGift(id: gift.id, giftId: gift.giftId, title: gift.title, number: gift.number, slug: gift.slug, owner: gift.owner, attributes: gift.attributes, availability: gift.availability, giftAddress: gift.giftAddress, resellAmounts: prices, resellForTonOnly: gift.resellForTonOnly, releasedBy: gift.releasedBy, valueAmount: gift.valueAmount, valueCurrency: gift.valueCurrency, valueUsdAmount: gift.valueUsdAmount, flags: gift.flags, themePeerId: gift.themePeerId, peerColor: gift.peerColor, hostPeerId: gift.hostPeerId, minOfferStars: gift.minOfferStars, craftChancePermille: gift.craftChancePermille)
    }

    func buyLocalGiftWithGrams(accountId: EnginePeer.Id, recipientPeerId: EnginePeer.Id, gift: StarGift.UniqueGift, price: Int64, requireListing: Bool, now: Int32) -> VisualGramGiftPurchaseResult {
        guard price > 0, localGramPrice(accountId: accountId, gift: gift) == price else { return .priceChanged }
        var result: VisualGramGiftPurchaseResult = .unavailable
        self.updateValues { values in
            let buyerKey = String(accountId.toInt64())
            guard var buyer = values[buyerKey], buyer.enabled, let balance = buyer.grams else { result = .invalid; return }
            guard balance >= price else { result = .insufficientBalance; return }
            var seller: (String, Int)?
            for (key, value) in values {
                if let index = value.gifts.firstIndex(where: { $0.direction == .received && $0.isHistoryOnly != true && $0.assetIdentifier == "unique:" + gift.slug }) { seller = (key, index); break }
            }
            if let (key, index) = seller {
                guard key != buyerKey, key != String(recipientPeerId.toInt64()), let sellerRawId = Int64(key), var sellerValue = values[key], sellerValue.enabled,
                      let askingStars = sellerValue.gifts[index].resaleStars, askingStars > 0,
                      let rate = buyer.gramStarsPerUnit, rate > 0 else { return }
                var raw = Decimal(askingStars) * Decimal(Self.gramScale) / Decimal(rate)
                var rounded = Decimal(); NSDecimalRound(&rounded, &raw, 0, .up)
                guard rounded == Decimal(price) else { result = .priceChanged; return }
                let (credited, overflow) = (sellerValue.grams ?? 0).addingReportingOverflow(price)
                guard !overflow else { result = .invalid; return }
                buyer.grams = balance - price
                var payments = buyer.gramHistory ?? []
                payments.append(.init(id: UUID().uuidString, date: now, amount: -price, kind: .purchase, title: nil, peerId: sellerRawId, gift: .unique(gift)))
                buyer.gramHistory = payments
                sellerValue.grams = credited
                var revenue = sellerValue.gramHistory ?? []
                revenue.append(.init(id: UUID().uuidString, date: now, amount: price, kind: .sale, title: nil, peerId: accountId.toInt64(), gift: .unique(gift)))
                sellerValue.gramHistory = revenue
                values[buyerKey] = buyer; values[key] = sellerValue
                Self.moveLocalGift(values: &values, ownerId: EnginePeer.Id(sellerRawId), index: index, recipientId: recipientPeerId, now: now, purchaseGrams: price, buyerId: accountId)
            } else {
                guard !requireListing, !values.values.contains(where: { $0.gifts.contains { $0.assetIdentifier == "unique:" + gift.slug } }) else { return }
                buyer.grams = balance - price
                var history = buyer.gramHistory ?? []
                history.append(.init(id: UUID().uuidString, date: now, amount: -price, kind: .purchase, title: nil, peerId: recipientPeerId.toInt64(), gift: .unique(gift)))
                buyer.gramHistory = history
                values[buyerKey] = buyer
                let targetKey = String(recipientPeerId.toInt64())
                var target = values[targetKey] ?? VisualGramAppearance()
                target.enabled = true
                var local = VisualGramGift(gift: .unique(gift), counterpartyId: accountId.toInt64(), date: now, text: "")
                local.purchaseGrams = price; local.purchaseBuyerId = accountId.toInt64()
                target.gifts.append(local); values[targetKey] = target
                if recipientPeerId != accountId {
                    local.direction = .sent; local.counterpartyId = recipientPeerId.toInt64(); local.isHistoryOnly = true
                    values[buyerKey]?.gifts.append(local)
                }
            }
            result = .success
        }
        return result
    }
}
