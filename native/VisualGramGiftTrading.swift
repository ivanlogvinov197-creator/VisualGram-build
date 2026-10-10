import Foundation

public enum VisualGramGiftPurchaseResult: Equatable {
    case success, insufficientBalance, unavailable, priceChanged, invalid
}

public extension VisualGramLocalAppearance {
    static let localGiftTransferStars: Int64 = 25

    static func recordStarsTransaction(value: inout VisualGramAppearance, amount: Int64, kind: VisualGramGift.StarsTransaction.Kind, peerId: EnginePeer.Id?, gift: StarGift?, title: String? = nil, now: Int32) {
        guard amount != 0 else { return }
        var history = value.starsHistory ?? []
        history.append(.init(id: UUID().uuidString, date: now, amount: amount, kind: kind, title: title, peerId: peerId?.toInt64(), gift: gift))
        value.starsHistory = history
    }

    func localReference(messageId: EngineMessage.Id) -> StarGiftReference? {
        guard messageId.namespace == Int32.max - 42 else { return nil }
        var historyReference: StarGiftReference?
        for (key, value) in self.snapshotValues() {
            guard let rawId = Int64(key) else { continue }
            for gift in value.gifts {
                let reference = gift.reference(accountId: EnginePeer.Id(rawId))
                if case let .message(id) = reference, id.id == messageId.id {
                    if gift.direction == .received && gift.isHistoryOnly != true { return reference }
                    historyReference = historyReference ?? reference
                }
            }
        }
        return historyReference
    }

    func canManageLocalGift(accountId: EnginePeer.Id, reference: StarGiftReference?) -> Bool {
        guard case let .message(id) = reference, id.peerId == accountId,
              let gift = self.localGift(accountId: accountId, reference: reference) else { return false }
        return gift.direction == .received && gift.isHistoryOnly != true
    }

    func localReference(slug: String) -> StarGiftReference? {
        for (key, value) in self.snapshotValues() {
            guard let rawId = Int64(key), value.enabled else { continue }
            for local in value.gifts where local.direction == .received && local.isHistoryOnly != true {
                if case let .unique(gift) = local.gift, gift.slug == slug {
                    return local.reference(accountId: EnginePeer.Id(rawId))
                }
            }
        }
        return nil
    }

    // All ownership, history and balance changes are committed under the store's lock.
    @discardableResult
    func transferLocalGift(accountId: EnginePeer.Id, reference: StarGiftReference?, recipientPeerId: EnginePeer.Id, now: Int32) -> Bool {
        guard Self.isLocalReference(reference), recipientPeerId != accountId,
              case let .message(id) = reference, id.peerId == accountId else { return false }
        var transferred = false
        self.updateValues { values in
            let key = String(accountId.toInt64())
            guard let index = values[key]?.gifts.firstIndex(where: { $0.reference(accountId: accountId) == reference }),
                  let local = values[key]?.gifts[index], local.direction == .received,
                  local.isHistoryOnly != true, case .unique = local.gift else { return }
            guard var owner = values[key], owner.enabled, let balance = owner.stars, balance >= Self.localGiftTransferStars else { return }
            owner.stars = balance - Self.localGiftTransferStars
            Self.recordStarsTransaction(value: &owner, amount: -Self.localGiftTransferStars, kind: .transfer, peerId: recipientPeerId, gift: local.gift, now: now)
            values[key] = owner
            Self.moveLocalGift(values: &values, ownerId: accountId, index: index, recipientId: recipientPeerId, now: now)
            transferred = true
        }
        return transferred
    }

    @discardableResult
    func listLocalGift(accountId: EnginePeer.Id, reference: StarGiftReference?, price: Int64?) -> Bool {
        guard price == nil || (price! > 0 && price! <= Int64(Int32.max)),
              self.canManageLocalGift(accountId: accountId, reference: reference),
              case .unique = self.localGift(accountId: accountId, reference: reference)?.gift else { return false }
        var changed = false
        self.updateValues { values in
            let key = String(accountId.toInt64())
            guard let index = values[key]?.gifts.firstIndex(where: { $0.reference(accountId: accountId) == reference && $0.direction == .received && $0.isHistoryOnly != true }) else { return }
            values[key]?.gifts[index].resaleStars = price
            changed = true
        }
        return changed
    }

    func buyLocalGift(accountId: EnginePeer.Id, recipientPeerId: EnginePeer.Id, gift: StarGift.UniqueGift, price: Int64, requireListing: Bool, now: Int32) -> VisualGramGiftPurchaseResult {
        guard price > 0, price <= Int64(Int32.max) else { return .invalid }
        var result: VisualGramGiftPurchaseResult = .unavailable
        self.updateValues { values in
            let buyerKey = String(accountId.toInt64())
            guard var buyer = values[buyerKey], buyer.enabled, let balance = buyer.stars else { result = .invalid; return }
            guard balance >= price else { result = .insufficientBalance; return }
            var seller: (EnginePeer.Id, Int)?
            for (key, value) in values where value.enabled {
                guard let rawId = Int64(key) else { continue }
                if let index = value.gifts.firstIndex(where: { local in
                    guard local.direction == .received, local.isHistoryOnly != true, case let .unique(unique) = local.gift else { return false }
                    return unique.slug == gift.slug
                }) { seller = (EnginePeer.Id(rawId), index); break }
            }
            if let (sellerId, index) = seller {
                guard sellerId != accountId, sellerId != recipientPeerId else { return }
                let sellerKey = String(sellerId.toInt64())
                guard values[sellerKey]?.gifts[index].resaleStars == price else { result = .priceChanged; return }
                let (newBalance, overflow) = (values[sellerKey]?.stars ?? 0).addingReportingOverflow(price)
                guard !overflow else { result = .invalid; return }
                buyer.stars = balance - price
                Self.recordStarsTransaction(value: &buyer, amount: -price, kind: .purchase, peerId: sellerId, gift: .unique(gift), now: now)
                values[buyerKey] = buyer
                values[sellerKey]?.stars = newBalance
                if var sellerValue = values[sellerKey] {
                    Self.recordStarsTransaction(value: &sellerValue, amount: price, kind: .sale, peerId: accountId, gift: .unique(gift), now: now)
                    values[sellerKey] = sellerValue
                }
                Self.moveLocalGift(values: &values, ownerId: sellerId, index: index, recipientId: recipientPeerId, now: now, purchaseStars: price, buyerId: accountId)
            } else {
                // A catalog purchase creates a local copy. Existing local assets cannot be bought twice.
                guard !requireListing, !values.values.contains(where: { $0.gifts.contains { $0.assetIdentifier == "unique:\(gift.slug)" } }) else { return }
                buyer.stars = balance - price
                Self.recordStarsTransaction(value: &buyer, amount: -price, kind: .purchase, peerId: recipientPeerId, gift: .unique(gift), now: now)
                values[buyerKey] = buyer
                let targetKey = String(recipientPeerId.toInt64())
                var target = values[targetKey] ?? VisualGramAppearance()
                target.enabled = true
                var local = VisualGramGift(gift: .unique(gift), counterpartyId: accountId.toInt64(), date: now, text: "")
                local.localIdentifier = UUID().uuidString
                local.purchaseStars = price
                local.purchaseBuyerId = accountId.toInt64()
                target.gifts.append(local)
                values[targetKey] = target
                if recipientPeerId != accountId {
                    var outgoing = local
                    outgoing.direction = .sent
                    outgoing.counterpartyId = recipientPeerId.toInt64()
                    outgoing.isHistoryOnly = true
                    values[buyerKey]?.gifts.append(outgoing)
                }
            }
            result = .success
        }
        return result
    }

    func buyLocalOrdinaryGift(accountId: EnginePeer.Id, recipientPeerId: EnginePeer.Id, gift: StarGift.Gift, text: String, includeUpgrade: Bool, preview: StarGiftUpgradePreview?, hasPremium: Bool = false, now: Int32) -> VisualGramGiftPurchaseResult {
        guard gift.price > 0, gift.soldOut == nil, (gift.availability?.remains ?? 1) > 0,
              (gift.perUserLimit?.remains ?? 1) > 0, !gift.flags.contains(.isAuction),
              (gift.lockedUntilDate ?? 0) <= now else { return .unavailable }
        let (price, overflow) = gift.price.addingReportingOverflow(includeUpgrade ? (gift.upgradeStars ?? 0) : 0)
        guard !overflow, price > 0, price <= Int64(Int32.max) else { return .invalid }
        let purchased: StarGift
        if includeUpgrade {
            guard let preview, let unique = Self.makeUpgradedGift(gift, preview: preview, ownerId: recipientPeerId) else { return .unavailable }
            purchased = .unique(unique)
        } else { purchased = .generic(gift) }
        var result: VisualGramGiftPurchaseResult = .invalid
        self.updateValues { values in
            let buyerKey = String(accountId.toInt64()), targetKey = String(recipientPeerId.toInt64())
            guard var buyer = values[buyerKey], buyer.enabled, let balance = buyer.stars else { return }
            if gift.flags.contains(.requiresPremium), !buyer.premium && !hasPremium { result = .unavailable; return }
            let countKey = String(gift.id)
            let previous = Int(buyer.giftPurchaseCounts?[countKey] ?? 0)
            if let limit = gift.perUserLimit, previous >= Int(limit.remains) { result = .unavailable; return }
            if let availability = gift.availability, previous >= Int(availability.remains) { result = .unavailable; return }
            guard balance >= price else { result = .insufficientBalance; return }
            buyer.stars = balance - price
            Self.recordStarsTransaction(value: &buyer, amount: -price, kind: .purchase, peerId: recipientPeerId, gift: purchased, now: now)
            buyer.giftPurchaseCounts = buyer.giftPurchaseCounts ?? [:]
            buyer.giftPurchaseCounts?[countKey] = Int32(clamping: previous + 1)
            values[buyerKey] = buyer
            var target = values[targetKey] ?? VisualGramAppearance()
            target.enabled = true
            var local = VisualGramGift(gift: purchased, counterpartyId: accountId.toInt64(), date: now, text: text)
            local.purchaseStars = price
            local.purchaseBuyerId = accountId.toInt64()
            target.gifts.append(local)
            values[targetKey] = target
            if recipientPeerId != accountId {
                local.direction = .sent
                local.counterpartyId = recipientPeerId.toInt64()
                local.isHistoryOnly = true
                values[buyerKey]?.gifts.append(local)
            }
            result = .success
        }
        return result
    }

    private static func moveLocalGift(values: inout [String: VisualGramAppearance], ownerId: EnginePeer.Id, index: Int, recipientId: EnginePeer.Id, now: Int32, purchaseStars: Int64? = nil, buyerId: EnginePeer.Id? = nil) {
        let ownerKey = String(ownerId.toInt64()), targetKey = String(recipientId.toInt64())
        guard var owner = values[ownerKey], owner.gifts.indices.contains(index) else { return }
        let original = owner.gifts[index]
        var history = original
        history.localIdentifier = "history:\(UUID().uuidString)"
        history.isHistoryOnly = true
        history.resaleStars = nil
        owner.gifts[index] = history
        var outgoing = original
        outgoing.localIdentifier = "sent:\(UUID().uuidString)"
        outgoing.direction = .sent
        outgoing.counterpartyId = recipientId.toInt64()
        outgoing.date = now
        outgoing.isTransferred = true
        outgoing.isHistoryOnly = true
        outgoing.resaleStars = nil
        outgoing.purchaseStars = buyerId == recipientId ? purchaseStars : nil
        outgoing.purchaseBuyerId = buyerId == recipientId ? buyerId?.toInt64() : nil
        owner.gifts.append(outgoing)
        if case let .unique(gift) = original.gift, case let .starGift(id, _, _, _, _, _, _, _, _) = owner.emojiStatus?.content, id == gift.id {
            owner.overridesEmojiStatus = true
            owner.emojiStatus = nil
        }
        values[ownerKey] = owner
        var target = values[targetKey] ?? VisualGramAppearance()
        target.enabled = true
        target.gifts.removeAll { $0.direction == .received && $0.isHistoryOnly != true && $0.assetIdentifier == original.assetIdentifier }
        var received = original
        received.localIdentifier = original.identifier
        received.direction = .received
        received.counterpartyId = ownerId.toInt64()
        if let buyerId, buyerId != recipientId { received.counterpartyId = buyerId.toInt64() }
        received.date = now
        received.isHistoryOnly = false
        received.isTransferred = true
        received.resaleStars = nil
        received.purchaseStars = purchaseStars
        received.purchaseBuyerId = buyerId?.toInt64()
        received.pinnedToTop = false
        received.savedToProfile = true
        received.collectionIds = nil
        target.gifts.append(received)
        values[targetKey] = target
        if let buyerId, buyerId != recipientId && buyerId != ownerId {
            var purchase = received
            purchase.direction = .sent
            purchase.counterpartyId = recipientId.toInt64()
            purchase.isHistoryOnly = true
            values[String(buyerId.toInt64())]?.gifts.append(purchase)
        }
    }

    func hasLocalGiftListings(giftId: Int64) -> Bool {
        return self.snapshotValues().values.contains { value in
            value.enabled && value.gifts.contains { local in
                guard local.direction == .received, local.isHistoryOnly != true, (local.resaleStars ?? 0) > 0, case let .unique(gift) = local.gift else { return false }
                return gift.giftId == giftId
            }
        }
    }

    func localMarketState(_ server: ResaleGiftsContext.State, giftId: Int64, accountId: EnginePeer.Id) -> ResaleGiftsContext.State {
        var result = server
        var local: [StarGift] = []
        for (key, value) in self.snapshotValues() where value.enabled {
            guard let rawId = Int64(key) else { continue }
            for item in value.gifts where item.direction == .received && item.isHistoryOnly != true && (item.resaleStars ?? 0) > 0 {
                if case let .unique(gift) = item.gift, gift.giftId == giftId {
                    let displayed = item.displayGift(accountId: EnginePeer.Id(rawId))
                    if server.filterAttributes.allSatisfy({ attribute in
                        switch attribute {
                        case let .model(id): return gift.attributes.contains { if case let .model(_, file, _, _) = $0 { return file.fileId.id == id }; return false }
                        case let .pattern(id): return gift.attributes.contains { if case let .pattern(_, file, _) = $0 { return file.fileId.id == id }; return false }
                        case let .backdrop(id): return gift.attributes.contains { if case let .backdrop(_, value, _, _, _, _, _) = $0 { return value == id }; return false }
                        }
                    }) { local.append(displayed) }
                }
            }
        }
        let localSlugs = Set(local.compactMap { if case let .unique(gift) = $0 { return gift.slug }; return nil as String? })
        result.gifts = local + server.gifts.filter { if case let .unique(gift) = $0 { return !localSlugs.contains(gift.slug) }; return true }
        if server.sorting == .value {
            result.gifts.sort {
                guard case let .unique(a) = $0, case let .unique(b) = $1 else { return false }
                return (a.resellAmounts?.first(where: { $0.currency == .stars })?.amount.value ?? Int64.max) < (b.resellAmounts?.first(where: { $0.currency == .stars })?.amount.value ?? Int64.max)
            }
        } else if server.sorting == .number {
            result.gifts.sort { guard case let .unique(a) = $0, case let .unique(b) = $1 else { return false }; return a.number < b.number }
        }
        result.count = max(Int32(result.gifts.count), (server.count ?? 0) + Int32(local.count))
        return result
    }
}
