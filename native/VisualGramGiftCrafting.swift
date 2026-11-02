import Foundation

public enum VisualGramCraftResult { case success(VisualGramGift), failure(CraftStarGiftError) }

public extension VisualGramLocalAppearance {
    func localCraftReference(accountId: EnginePeer.Id, gift: StarGift.UniqueGift) -> StarGiftReference? {
        let value = self.appearance(accountId: accountId)
        guard value.enabled else { return nil }
        return value.gifts.first(where: { local in
            guard local.direction == .received, local.isHistoryOnly != true, case let .unique(unique) = local.gift else { return false }
            return unique.slug == gift.slug
        })?.reference(accountId: accountId)
    }
    func updateLocalCraftMetadata(accountId: EnginePeer.Id, reference: StarGiftReference, gift: StarGift.UniqueGift) {
        self.update(accountId: accountId) { value in
            guard let index = value.gifts.firstIndex(where: { $0.reference(accountId: accountId) == reference && $0.direction == .received && $0.isHistoryOnly != true && $0.isCrafted != true }),
                  case let .unique(existing) = value.gifts[index].gift,
                  existing.slug == gift.slug, existing.giftId == gift.giftId else { return }
            // Refresh catalog metadata only. Keep local receipt, ownership, order,
            // sale price and any separate locally configured unlock date.
            value.gifts[index].gift = .unique(gift)
        }
    }
    func craftableLocalGifts(accountId: EnginePeer.Id, giftId: Int64, now: Int32) -> [VisualGramGift] {
        let value = self.appearance(accountId: accountId)
        guard value.enabled else { return [] }
        return value.gifts.filter { local in
            guard local.direction == .received, local.isHistoryOnly != true,
                  (local.canCraftAt ?? 0) <= now, case let .unique(gift) = local.gift else { return false }
            return gift.giftId == giftId && (gift.craftChancePermille ?? 0) > 0 && !gift.flags.contains(.isBurned)
        }
    }

    // All validation precedes consumption. Only owned local references can enter this path.
    func craftLocalGifts(accountId: EnginePeer.Id, references: [StarGiftReference], attributes: [StarGift.UniqueGift.Attribute], attributePermilles: [[Int32]], now: Int32, random: (Range<Int>) -> Int = { Int.random(in: $0) }) -> VisualGramCraftResult {
        guard (1...4).contains(references.count), Set(references).count == references.count,
              references.allSatisfy({ Self.isLocalReference($0) }),
              attributePermilles.indices.contains(references.count - 1),
              attributePermilles[references.count - 1].count >= references.count else { return .failure(.unavailable) }
        let models = attributes.filter { if case let .model(_, _, _, crafted) = $0 { return crafted }; return false }
        let patterns = attributes.filter { $0.attributeType == .pattern }
        let backdrops = attributes.filter { $0.attributeType == .backdrop }
        guard !models.isEmpty, !patterns.isEmpty, !backdrops.isEmpty else { return .failure(.unavailable) }
        var result: VisualGramCraftResult = .failure(.unavailable)
        self.updateValues { values in
            let key = String(accountId.toInt64())
            guard var owner = values[key], owner.enabled else { return }
            var inputs: [VisualGramGift] = []
            var uniques: [StarGift.UniqueGift] = []
            for reference in references {
                guard case let .message(id) = reference, id.peerId == accountId,
                      let local = owner.gifts.first(where: { $0.reference(accountId: accountId) == reference }),
                      local.direction == .received, local.isHistoryOnly != true,
                      case let .unique(gift) = local.gift, !gift.flags.contains(.isBurned),
                      let chance = gift.craftChancePermille, chance > 0, chance <= 1000,
                      uniques.first.map({ $0.giftId == gift.giftId }) ?? true else { return }
                if let time = local.canCraftAt, now < time { result = .failure(.tooEarly(time)); return }
                inputs.append(local); uniques.append(gift)
            }
            let chance = min(1000, uniques.reduce(0) { $0 + Int($1.craftChancePermille ?? 0) })
            let succeeded = random(0..<1000) < chance
            let consumed = Set(inputs.map { $0.identifier })
            for index in owner.gifts.indices where consumed.contains(owner.gifts[index].identifier) {
                owner.gifts[index].isHistoryOnly = true
                owner.gifts[index].consumedAt = now
                owner.gifts[index].resaleStars = nil
                owner.gifts[index].resaleGrams = nil
                owner.gifts[index].savedToProfile = false
                owner.gifts[index].pinnedToTop = false
                owner.gifts[index].collectionIds = nil
            }
            owner.gramCardGiftIds?.removeAll { consumed.contains($0) }
            owner.gramCardPlacements = owner.gramCardPlacements?.filter { !consumed.contains($0.key) }
            if let id = owner.gramCardBackgroundId, consumed.contains(id) { owner.gramCardBackgroundId = nil }
            owner.giftOrder?.removeAll { consumed.contains($0) }
            if case let .starGift(id, _, _, _, _, _, _, _, _) = owner.emojiStatus?.content, uniques.contains(where: { $0.id == id }) {
                owner.overridesEmojiStatus = true; owner.emojiStatus = nil
            }
            if succeeded, let first = uniques.first {
                func choose(_ type: StarGift.UniqueGift.Attribute.AttributeType, fallback: [StarGift.UniqueGift.Attribute]) -> StarGift.UniqueGift.Attribute {
                    let original = uniques.compactMap { $0.attributes.first(where: { $0.attributeType == type }) }
                    var groups: [(StarGift.UniqueGift.Attribute, Int)] = []
                    for attr in original {
                        if let index = groups.firstIndex(where: { $0.0 == attr }) { groups[index].1 += 1 }
                        else { groups.append((attr, 1)) }
                    }
                    var roll = random(0..<1000)
                    for (attr, count) in groups {
                        let probability = max(0, Int(attributePermilles[inputs.count - 1][count - 1]))
                        if roll < probability { return attr }; roll -= probability
                    }
                    return fallback[random(0..<fallback.count)]
                }
                let model = models[random(0..<models.count)]
                let pattern = choose(.pattern, fallback: patterns)
                let backdrop = choose(.backdrop, fallback: backdrops)
                let unique = StarGift.UniqueGift(id: first.id, giftId: first.giftId, title: first.title, number: first.number, slug: first.slug, owner: .peerId(accountId), attributes: [model, pattern, backdrop], availability: first.availability, giftAddress: nil, resellAmounts: nil, resellForTonOnly: false, releasedBy: first.releasedBy, valueAmount: first.valueAmount, valueCurrency: first.valueCurrency, valueUsdAmount: first.valueUsdAmount, flags: [], themePeerId: first.themePeerId, peerColor: first.peerColor, hostPeerId: nil, minOfferStars: nil, craftChancePermille: nil)
                var crafted = inputs[0]
                crafted.localIdentifier = UUID().uuidString; crafted.gift = .unique(unique)
                crafted.date = now; crafted.counterpartyId = nil; crafted.text = ""
                crafted.isHistoryOnly = false; crafted.isCrafted = true; crafted.canCraftAt = nil
                crafted.savedToProfile = true; crafted.pinnedToTop = false; crafted.collectionIds = nil
                crafted.resaleStars = nil; crafted.resaleGrams = nil; crafted.purchaseStars = nil; crafted.purchaseGrams = nil; crafted.purchaseBuyerId = nil
                owner.gifts.append(crafted)
                result = .success(crafted)
            } else { result = .failure(.craftFailed) }
            values[key] = owner
        }
        return result
    }
}
