import Foundation
import CryptoKit

public enum VisualGramGramTransferResult: Equatable {
    case sent, insufficientBalance, invalidRecipient, overflow, unavailable
}

public enum VisualGramBalanceHistory: Equatable {
    case stars, grams

    fileprivate var entries: WritableKeyPath<VisualGramAppearance, [VisualGramGift.StarsTransaction]?> {
        switch self {
        case .stars: return \.starsHistory
        case .grams: return \.gramHistory
        }
    }

    fileprivate var order: WritableKeyPath<VisualGramAppearance, [String]?> {
        switch self {
        case .stars: return \.starsHistoryOrder
        case .grams: return \.gramHistoryOrder
        }
    }

    public func displayedEntries(in appearance: VisualGramAppearance, editorOrder: Bool = false) -> [VisualGramGift.StarsTransaction] {
        let visible = (appearance[keyPath: self.entries] ?? []).reversed().compactMap { entry -> VisualGramGift.StarsTransaction? in
            guard entry.hiddenFromBalanceHistory != true else { return nil }
            guard let edit = entry.historyEdit else { return entry }
            var displayed = entry
            displayed.amount = edit.amount
            displayed.date = edit.date
            displayed.comment = edit.comment
            return displayed
        }.sorted { $0.date > $1.date }
        guard editorOrder, let order = appearance[keyPath: self.order] else { return visible }
        let savedIds = Set(order)
        var entriesById: [String: VisualGramGift.StarsTransaction] = [:]
        for entry in visible { entriesById[entry.id] = entry }
        return visible.filter { !savedIds.contains($0.id) } + order.compactMap { entriesById[$0] }
    }
}

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

    func saveBalanceHistoryOrder(target: EnginePeer.Id, currency: VisualGramBalanceHistory, ids: [String]) -> Bool {
        var saved = false
        self.updateValues(recordOperations: false) { values in
            let key = String(target.toInt64())
            guard var value = values[key] else { return }
            let current = currency.displayedEntries(in: value).map(\.id)
            let requested = Set(ids)
            guard ids.count == current.count, requested.count == ids.count, requested == Set(current) else { return }
            value[keyPath: currency.order] = ids
            values[key] = value
            saved = true
        }
        return saved
    }

    func editBalanceHistoryEntry(target: EnginePeer.Id, currency: VisualGramBalanceHistory, id: String, edit: VisualGramGift.StarsTransaction.HistoryEdit) -> Bool {
        guard edit.amount != 0, edit.amount != Int64.min else { return false }
        return self.updateBalanceHistoryEntry(target: target, currency: currency, id: id) {
            guard ($0.amount < 0) == (edit.amount < 0) else { return false }
            $0.historyEdit = edit
            return true
        }
    }

    func deleteBalanceHistoryEntry(target: EnginePeer.Id, currency: VisualGramBalanceHistory, id: String) -> Bool {
        self.updateBalanceHistoryEntry(target: target, currency: currency, id: id) {
            $0.hiddenFromBalanceHistory = true
            return true
        }
    }

    private func updateBalanceHistoryEntry(target: EnginePeer.Id, currency: VisualGramBalanceHistory, id: String, _ update: (inout VisualGramGift.StarsTransaction) -> Bool) -> Bool {
        var saved = false
        self.updateValues(recordOperations: false) { values in
            let key = String(target.toInt64())
            guard var value = values[key], var entries = value[keyPath: currency.entries],
                  let index = entries.firstIndex(where: { $0.id == id && $0.hiddenFromBalanceHistory != true }),
                  update(&entries[index]) else { return }
            if entries[index].hiddenFromBalanceHistory == true {
                value[keyPath: currency.order]?.removeAll { $0 == id }
            }
            value[keyPath: currency.entries] = entries
            values[key] = value
            saved = true
        }
        return saved
    }

    static func visualWalletAddress(peerId: EnginePeer.Id) -> String {
        let number = UInt64(bitPattern: peerId.toInt64())
        let peerBytes = (0 ..< 8).map { UInt8(truncatingIfNeeded: number >> ((7 - $0) * 8)) }
        let entropy = Array(SHA256.hash(data: Data("DuckGram wallet:".utf8) + Data(peerBytes)))
        let maskedPeer = zip(peerBytes, entropy.prefix(8)).map { $0.0 ^ $0.1 }
        var bytes: [UInt8] = [0x51, 0]
        bytes.append(contentsOf: entropy.prefix(24))
        bytes.append(contentsOf: maskedPeer)
        // Keep TON's visible format but deliberately fail its checksum validation.
        let checksum = bytes.reduce(UInt16(0)) { crc, byte in
            (0 ..< 8).reduce(crc ^ (UInt16(byte) << 8)) { value, _ in
                (value << 1) ^ (value & 0x8000 == 0 ? 0 : 0x1021)
            }
        } ^ UInt16.max
        bytes += [UInt8(checksum >> 8), UInt8(truncatingIfNeeded: checksum)]
        return Data(bytes).base64EncodedString()
            .replacingOccurrences(of: "+", with: "-")
            .replacingOccurrences(of: "/", with: "_")
    }

    static func visualWalletPeer(address: String) -> EnginePeer.Id? {
        let number: UInt64
        if address.hasPrefix("UQ"), address.utf8.count == 48,
           let data = Data(base64Encoded: address.replacingOccurrences(of: "-", with: "+").replacingOccurrences(of: "_", with: "/")),
           data.count == 36 {
            let bytes = Array(data)
            number = zip(bytes[26 ..< 34], bytes[2 ..< 10]).reduce(UInt64(0)) { value, pair in
                (value << 8) | UInt64(pair.0 ^ pair.1)
            }
        } else if let legacyNumber = Self.legacyVisualWalletNumber(address: address) {
            number = legacyNumber
        } else {
            return nil
        }
        guard number > 0, number < (UInt64(1) << 59), (number >> 32) & 7 == 0 else { return nil }
        let peerId = EnginePeer.Id(Int64(number))
        guard peerId.namespace == Namespaces.Peer.CloudUser else { return nil }
        return address.hasPrefix("dg") || Self.visualWalletAddress(peerId: peerId) == address ? peerId : nil
    }

    private static func legacyVisualWalletNumber(address: String) -> UInt64? {
        guard address.hasPrefix("dg") else { return nil }
        let payload = address.dropFirst(2)
        guard !payload.isEmpty, payload.first != "a", payload.count <= 16 else { return nil }
        let alphabet = Array("abcdefghijklmnop")
        var number = UInt64(0)
        for character in payload {
            guard let digit = alphabet.firstIndex(of: character) else { return nil }
            number = (number << 4) | UInt64(digit)
        }
        return number
    }

    func transferLocalGrams(accountId: EnginePeer.Id, toAddress address: String, amount: Int64, comment: String?, now: Int32, transferId: String) -> VisualGramGramTransferResult {
        if let peer = Self.visualWalletPeer(address: address) {
            return self.transferLocalGrams(accountId: accountId, to: peer, amount: amount, comment: comment, now: now, transferId: transferId)
        }
        guard !address.isEmpty, amount > 0 else { return .invalidRecipient }
        var result: VisualGramGramTransferResult = .unavailable
        self.updateValues(recordOperations: false) { values in
            let key = String(accountId.toInt64())
            guard var sender = values[key], sender.enabled, let balance = sender.grams, amount <= balance else {
                result = .insufficientBalance
                return
            }
            sender.grams = balance - amount
            var history = sender.gramHistory ?? []
            history.append(.init(id: transferId, date: now, amount: -amount, kind: .transfer, title: nil, peerId: nil, gift: nil, comment: comment, walletAddress: address))
            sender.gramHistory = history
            values[key] = sender
            result = .sent
        }
        return result
    }

    func localGramBalance(accountId: EnginePeer.Id) -> Int64? {
        let value = self.appearance(accountId: accountId)
        return value.enabled ? value.grams : nil
    }

    func transferLocalGrams(accountId: EnginePeer.Id, to recipient: EnginePeer.Id, amount: Int64, comment: String?, now: Int32, transferId: String = UUID().uuidString) -> VisualGramGramTransferResult {
        guard recipient != accountId, recipient.namespace == Namespaces.Peer.CloudUser else { return .invalidRecipient }
        guard amount > 0 else { return .unavailable }
        let senderKey = String(accountId.toInt64())
        let recipientKey = String(recipient.toInt64())
        var result: VisualGramGramTransferResult = .unavailable
        self.updateValues(recordOperations: false) { values in
            guard var sender = values[senderKey], sender.enabled, let balance = sender.grams, amount <= balance else {
                result = .insufficientBalance
                return
            }
            var receiver = values[recipientKey] ?? VisualGramAppearance()
            let (credit, overflow) = (receiver.grams ?? 0).addingReportingOverflow(amount)
            guard !overflow else { result = .overflow; return }
            sender.grams = balance - amount
            receiver.grams = credit
            receiver.enabled = true
            var outgoing = sender.gramHistory ?? []
            var incoming = receiver.gramHistory ?? []
            outgoing.append(.init(id: transferId, date: now, amount: -amount, kind: .transfer, title: "Исходящий перевод", peerId: recipient.toInt64(), gift: nil, comment: comment))
            incoming.append(.init(id: transferId, date: now, amount: amount, kind: .transfer, title: "Входящий перевод", peerId: accountId.toInt64(), gift: nil, comment: comment))
            sender.gramHistory = outgoing
            receiver.gramHistory = incoming
            values[senderKey] = sender
            values[recipientKey] = receiver
            result = .sent
        }
        return result
    }

    func topUpLocalGrams(accountId: EnginePeer.Id, amount: Int64, now: Int32) -> Bool {
        guard amount > 0 else { return false }
        var applied = false
        self.updateValues(recordOperations: false) { values in
            let key = String(accountId.toInt64())
            var value = values[key] ?? VisualGramAppearance()
            let (balance, overflow) = (value.grams ?? 0).addingReportingOverflow(amount)
            guard !overflow else { return }
            var history = value.gramHistory ?? []
            history.append(.init(id: UUID().uuidString, date: now, amount: amount, kind: .topUp, title: "Пополнение", peerId: nil, gift: nil))
            value.gramHistory = history
            value.grams = balance
            value.enabled = true
            values[key] = value
            applied = true
        }
        return applied
    }

    static func cardStickerAddress(_ gift: VisualGramGift) -> String { "visualgram:" + gift.identifier }

    static func resetGramCard(in value: inout VisualGramAppearance) {
        value.gramCardGiftIds = []; value.gramCardBackgroundId = nil; value.gramCardPlacements = [:]
    }

    func localGramPrice(accountId: EnginePeer.Id, gift: StarGift.UniqueGift, starsPerGram: Decimal? = nil) -> Int64? {
        return Self.gramPrice(gift: gift, starsPerUnit: starsPerGram)
    }

    private static func gramPrice(gift: StarGift.UniqueGift, starsPerUnit: Decimal?) -> Int64? {
        if let amount = gift.resellAmounts?.first(where: { $0.currency == .ton })?.amount.value, amount > 0 { return amount }
        guard !gift.resellForTonOnly, let stars = gift.resellAmounts?.first(where: { $0.currency == .stars })?.amount.value, stars > 0, let rate = starsPerUnit, rate > 0 else { return nil }
        var raw = Decimal(stars) * Decimal(Self.gramScale) / rate
        var rounded = Decimal(); NSDecimalRound(&rounded, &raw, 0, .down)
        guard rounded > 0, rounded <= Decimal(Int64.max) else { return nil }
        return NSDecimalNumber(decimal: rounded).int64Value
    }

    func displayWalletCard(accountId: EnginePeer.Id, peerId: EnginePeer.Id, server: WalletCard?, appearanceOverride: VisualGramAppearance? = nil) -> WalletCard? {
        guard VisualGramActivation.shared.hasAccess else { return server }
        let value = appearanceOverride ?? self.appearance(accountId: accountId, targetPeerId: peerId)
        guard value.enabled, let grams = value.grams else { return server }
        let selected = (value.gramCardGiftIds ?? []).prefix(10).compactMap { id -> VisualGramGift? in
            value.gifts.first { $0.identifier == id && $0.direction == .received && $0.isHistoryOnly != true }
        }
        let stickers = selected.enumerated().compactMap { index, local -> WalletCard.Sticker? in
            guard case let .unique(gift) = local.displayGift(accountId: peerId) else { return nil }
            let nft = WalletNftItem(collectionAddress: nil, address: Self.cardStickerAddress(local), ownerAddress: "", index: String(gift.number), name: gift.title, description: nil, image: nil, imageSmall: nil, contentUrl: nil, lottie: nil, attributes: nil, extra: nil, gift: gift)
            let placement = (value.gramCardPlacements?[local.identifier] ?? .init(x: 20.0 + Double(index % 4) * 20.0, y: 74.0 - Double(index / 4) * 24.0)).normalized
            let width = 83.4 / 361.0 * 100 * placement.scale
            return WalletCard.Sticker(coordinates: .init(x: placement.x, y: placement.y, width: width, height: width * 370 / 220, rotation: placement.angle, cornerRadius: nil), nft: nft)
        }
        var background: WalletNftItem?
        if let local = selected.first(where: { $0.identifier == value.gramCardBackgroundId }) {
            background = stickers.first(where: { $0.nft.address == Self.cardStickerAddress(local) })?.nft
        }
        return WalletCard(address: Self.visualWalletAddress(peerId: peerId), balance: grams, stickers: stickers, backgroundNft: background)
    }

    func giftForLocalPurchase(accountId: EnginePeer.Id, gift: StarGift.UniqueGift, starsPerGram: Decimal? = nil) -> StarGift.UniqueGift {
        guard !gift.resellForTonOnly, let grams = self.localGramPrice(accountId: accountId, gift: gift, starsPerGram: starsPerGram) else { return gift }
        var prices = gift.resellAmounts ?? []
        if !prices.contains(where: { $0.currency == .ton }) { prices.append(CurrencyAmount(amount: StarsAmount(value: grams, nanos: 0), currency: .ton)) }
        return StarGift.UniqueGift(id: gift.id, giftId: gift.giftId, title: gift.title, number: gift.number, slug: gift.slug, owner: gift.owner, attributes: gift.attributes, availability: gift.availability, giftAddress: gift.giftAddress, resellAmounts: prices, resellForTonOnly: gift.resellForTonOnly, releasedBy: gift.releasedBy, valueAmount: gift.valueAmount, valueCurrency: gift.valueCurrency, valueUsdAmount: gift.valueUsdAmount, flags: gift.flags, themePeerId: gift.themePeerId, peerColor: gift.peerColor, hostPeerId: gift.hostPeerId, minOfferStars: gift.minOfferStars, craftChancePermille: gift.craftChancePermille)
    }

    func buyLocalGiftWithGrams(accountId: EnginePeer.Id, recipientPeerId: EnginePeer.Id, gift: StarGift.UniqueGift, price: Int64, requireListing: Bool, now: Int32, starsPerGram: Decimal? = nil, text: String = "", nameHidden: Bool = false, entities: [MessageTextEntity]? = nil) -> VisualGramGiftPurchaseResult {
        guard price > 0 else { return .priceChanged }
        var result: VisualGramGiftPurchaseResult = .unavailable
        self.updateValues { values in
            let buyerKey = String(accountId.toInt64())
            guard var buyer = values[buyerKey], buyer.enabled, let balance = buyer.grams else { result = .invalid; return }
            guard Self.gramPrice(gift: gift, starsPerUnit: starsPerGram) == price else { result = .priceChanged; return }
            guard balance >= price else { result = .insufficientBalance; return }
            let seller = Self.localGiftSeller(values: values, gift: gift)
            if let (sellerId, index) = seller {
                let sellerRawId = sellerId.toInt64(), key = String(sellerId.toInt64())
                guard key != buyerKey, key != String(recipientPeerId.toInt64()), var sellerValue = values[key], sellerValue.enabled else { return }
                let listing = sellerValue.gifts[index]
                let asking: Int64?
                if let grams = listing.resaleGrams, grams > 0 { asking = grams }
                else if let stars = listing.resaleStars, stars > 0, let rate = starsPerGram, rate > 0 {
                    var raw = Decimal(stars) * Decimal(Self.gramScale) / rate
                    var rounded = Decimal(); NSDecimalRound(&rounded, &raw, 0, .down)
                    asking = rounded > 0 && rounded <= Decimal(Int64.max) ? NSDecimalNumber(decimal: rounded).int64Value : nil
                } else { asking = nil }
                guard asking == price else { result = .priceChanged; return }
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
            Self.applyPurchaseMessage(values: &values, slug: gift.slug, buyerId: accountId, now: now, text: text, nameHidden: nameHidden, entities: entities)
            result = .success
        }
        return result
    }
}
