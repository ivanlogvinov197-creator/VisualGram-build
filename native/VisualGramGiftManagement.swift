import Foundation

public struct VisualGramGiftCollection: Codable, Equatable {
    public var id: Int32
    public var title: String
    public init(id: Int32, title: String) { self.id = id; self.title = title }
}

public struct VisualGramScheduledGift: Codable, Equatable {
    public var id: String
    public var targetPeerId: Int64
    public var gift: VisualGramGift
    public var deliveryDate: Int32

    public init(targetPeerId: Int64, gift: VisualGramGift, deliveryDate: Int32) {
        self.id = UUID().uuidString
        self.targetPeerId = targetPeerId
        self.gift = gift
        self.deliveryDate = deliveryDate
    }
}

public extension VisualGramLocalAppearance {
    func chatGifts(accountId: EnginePeer.Id, peerId: EnginePeer.Id) -> [VisualGramGift] {
        let own = self.appearance(accountId: accountId)
        let other = self.appearance(accountId: accountId, targetPeerId: peerId)
        var result = own.enabled ? own.gifts.filter { $0.counterpartyId == peerId.toInt64() } : []
        if other.enabled, peerId != accountId {
            for gift in other.gifts where gift.counterpartyId == accountId.toInt64() {
                var reverse = gift
                reverse.direction = gift.direction == .received ? .sent : .received
                reverse.counterpartyId = peerId.toInt64()
                let alreadyPresent = result.contains { existing in
                    if existing.identifier == reverse.identifier { return true }
                    // A transferred NFT has separate sent and received records for one event.
                    if case .unique = reverse.gift {
                        return existing.assetIdentifier == reverse.assetIdentifier && existing.direction == reverse.direction && existing.date == reverse.date
                    }
                    return false
                }
                if !alreadyPresent { result.append(reverse) }
            }
        }
        return result
    }

    func rescheduleGift(id: String, deliveryDate: Int32) {
        self.updateValues { values in
            for key in Array(values.keys) {
                if let index = values[key]?.scheduledGifts?.firstIndex(where: { $0.id == id }) { values[key]?.scheduledGifts?[index].deliveryDate = deliveryDate }
            }
        }
    }

    func cancelScheduledGift(id: String) {
        self.updateValues { values in
            for key in Array(values.keys) { values[key]?.scheduledGifts?.removeAll { $0.id == id } }
        }
    }

    func addGift(accountId: EnginePeer.Id, targetPeerId: EnginePeer.Id, gift: VisualGramGift) {
        self.addGifts(accountId: accountId, targetPeerId: targetPeerId, gifts: [gift])
    }

    func addGifts(accountId: EnginePeer.Id, targetPeerId: EnginePeer.Id, gifts: [VisualGramGift]) {
        self.update(accountId: accountId, targetPeerId: targetPeerId) { value in
            value.enabled = true
            for gift in gifts { Self.insertGift(gift, into: &value) }
        }
    }

    @discardableResult
    func moveGift(accountId: EnginePeer.Id, targetPeerId: EnginePeer.Id, identifier: String, offset: Int) -> Bool {
        var moved = false
        self.update(accountId: accountId, targetPeerId: targetPeerId) { value in
            guard let index = value.gifts.firstIndex(where: { $0.identifier == identifier }) else { return }
            let destination = index + offset
            guard value.gifts.indices.contains(destination), destination != index else { return }
            let gift = value.gifts.remove(at: index)
            value.gifts.insert(gift, at: destination)
            moved = true
        }
        return moved
    }

    static func nftSlugs(from input: String) -> [String]? {
        let tokens = input.components(separatedBy: CharacterSet.whitespacesAndNewlines.union(CharacterSet(charactersIn: ",;"))).filter { !$0.isEmpty }
        guard !tokens.isEmpty, tokens.count <= 100 else { return nil }
        var result: [String] = []
        var seen = Set<String>()
        for token in tokens {
            let slug: String
            if token.contains("/") {
                let urlText = token.hasPrefix("http") ? token : "https://" + token
                guard let url = URL(string: urlText), ["t.me", "telegram.me"].contains(url.host?.lowercased() ?? ""), url.path.hasPrefix("/nft/") else { return nil }
                slug = url.lastPathComponent
            } else { slug = token }
            guard slug.range(of: "^[A-Za-z0-9]+-[0-9]+$", options: .regularExpression) != nil else { return nil }
            if seen.insert(slug.lowercased()).inserted { result.append(slug) }
        }
        return result
    }

    private static func insertGift(_ gift: VisualGramGift, into value: inout VisualGramAppearance) {
        value.gifts.removeAll { existing in
            if existing.identifier == gift.identifier { return true }
            if case .unique = gift.gift {
                return gift.direction == .received && existing.direction == .received && existing.isHistoryOnly != true && existing.assetIdentifier == gift.assetIdentifier
            }
            return false
        }
        value.gifts.append(gift)
    }

    func scheduleGift(accountId: EnginePeer.Id, targetPeerId: EnginePeer.Id, gift: VisualGramGift, deliveryDate: Int32) {
        self.scheduleGifts(accountId: accountId, targetPeerId: targetPeerId, gifts: [gift], deliveryDate: deliveryDate)
    }

    func scheduleGifts(accountId: EnginePeer.Id, targetPeerId: EnginePeer.Id, gifts: [VisualGramGift], deliveryDate: Int32) {
        self.updateValues { values in
            let targetKey = String(targetPeerId.toInt64())
            var target = values[targetKey] ?? VisualGramAppearance()
            target.enabled = true
            values[targetKey] = target
            let identifiers = Set(gifts.map { $0.identifier })
            for key in Array(values.keys) {
                values[key]?.scheduledGifts?.removeAll { $0.targetPeerId == targetPeerId.toInt64() && identifiers.contains($0.gift.identifier) }
            }
            let accountKey = String(accountId.toInt64())
            var value = values[accountKey] ?? VisualGramAppearance()
            var queue = value.scheduledGifts ?? []
            queue.append(contentsOf: gifts.map { VisualGramScheduledGift(targetPeerId: targetPeerId.toInt64(), gift: $0, deliveryDate: deliveryDate) })
            value.scheduledGifts = queue
            values[accountKey] = value
        }
    }

    // Removal and insertion share one persisted transaction, so reopening cannot deliver twice.
    @discardableResult
    func deliverScheduledGifts(accountId: EnginePeer.Id, now: Int32) -> [VisualGramScheduledGift] {
        guard (self.appearance(accountId: accountId).scheduledGifts ?? []).contains(where: { $0.deliveryDate <= now }) else { return [] }
        var delivered: [VisualGramScheduledGift] = []
        self.updateValues { values in
            let accountKey = String(accountId.toInt64())
            var value = values[accountKey] ?? VisualGramAppearance()
            delivered = (value.scheduledGifts ?? []).filter { $0.deliveryDate <= now }.sorted { $0.deliveryDate < $1.deliveryDate }
            value.scheduledGifts?.removeAll { $0.deliveryDate <= now }
            values[accountKey] = value
            for pending in delivered {
                var gift = pending.gift
                gift.date = pending.deliveryDate
                let key = String(pending.targetPeerId)
                var target = values[key] ?? VisualGramAppearance()
                Self.insertGift(gift, into: &target)
                values[key] = target
            }
        }
        return delivered
    }

    static func isLocalReference(_ reference: StarGiftReference?) -> Bool {
        if case let .message(messageId) = reference { return messageId.namespace == Int32.max - 42 }
        return false
    }

    func localGift(accountId: EnginePeer.Id, reference: StarGiftReference?) -> VisualGramGift? {
        guard Self.isLocalReference(reference), case let .message(id) = reference else { return nil }
        return self.appearance(accountId: accountId, targetPeerId: id.peerId).gifts.first { $0.reference(accountId: id.peerId) == reference }
    }

    // Read-only preview samples provide the original media and valid attribute combinations.
    // This creates a private visual collectible, without calling an upgrade/payment RPC.
    func upgradeLocalGift(accountId: EnginePeer.Id, reference: StarGiftReference?, preview: StarGiftUpgradePreview, keepOriginalInfo: Bool) -> ProfileGiftsContext.State.StarGift? {
        guard self.canManageLocalGift(accountId: accountId, reference: reference),
              let local = self.localGift(accountId: accountId, reference: reference), local.direction == .received,
              case let .generic(generic) = local.gift, case let .message(messageId) = reference else { return nil }
        guard let unique = Self.makeUpgradedGift(generic, preview: preview, ownerId: messageId.peerId) else { return nil }
        var result: VisualGramGift?
        self.update(accountId: accountId, targetPeerId: messageId.peerId) { value in
            guard let index = value.gifts.firstIndex(where: { $0.identifier == local.identifier }),
                  case .generic = value.gifts[index].gift else { return }
            value.gifts[index].localIdentifier = local.identifier
            value.gifts[index].gift = .unique(unique)
            value.gifts[index].hidesOriginalInfo = !keepOriginalInfo
            result = value.gifts[index]
        }
        return result?.profileGift(accountId: messageId.peerId, sender: nil)
    }

    static func makeUpgradedGift(_ generic: StarGift.Gift, preview: StarGiftUpgradePreview, ownerId: EnginePeer.Id) -> StarGift.UniqueGift? {
        guard generic.upgradeStars != nil,
              let model = preview.attributes.filter({ $0.attributeType == .model }).randomElement(),
              let pattern = preview.attributes.filter({ $0.attributeType == .pattern }).randomElement(),
              let backdrop = preview.attributes.filter({ $0.attributeType == .backdrop }).randomElement() else { return nil }
        let total = max(1, generic.availability?.total ?? 100000)
        return StarGift.UniqueGift(id: -Int64.random(in: 1 ... Int64.max), giftId: generic.id,
            title: generic.title ?? "Коллекционный подарок", number: Int32.random(in: 1 ... total),
            slug: "Gift-\(UUID().uuidString)", owner: .peerId(ownerId), attributes: [model, pattern, backdrop],
            availability: .init(issued: 1, total: total), giftAddress: nil, resellAmounts: nil,
            resellForTonOnly: false, releasedBy: generic.releasedBy, valueAmount: nil, valueCurrency: nil,
            valueUsdAmount: nil, flags: [], themePeerId: nil, peerColor: nil, hostPeerId: nil,
            minOfferStars: nil, craftChancePermille: nil)
    }

    @discardableResult
    func updateGift(accountId: EnginePeer.Id, reference: StarGiftReference?, change: (inout VisualGramGift) -> Void) -> Bool {
        guard self.canManageLocalGift(accountId: accountId, reference: reference), let gift = self.localGift(accountId: accountId, reference: reference), case let .message(id) = reference else { return false }
        self.update(accountId: accountId, targetPeerId: id.peerId) { value in
            if let index = value.gifts.firstIndex(where: { $0.identifier == gift.identifier }) { change(&value.gifts[index]) }
        }
        return true
    }

    func reorderGifts(accountId: EnginePeer.Id, targetPeerId: EnginePeer.Id? = nil, references: [StarGiftReference], updatePins: Bool = false) {
        let target = targetPeerId ?? accountId
        self.update(accountId: accountId, targetPeerId: target) { value in
            let ranked = references.compactMap { reference in value.gifts.first { $0.reference(accountId: target) == reference }?.identifier }
            if updatePins {
                for index in value.gifts.indices {
                    value.gifts[index].pinnedToTop = ranked.contains(value.gifts[index].identifier)
                }
            }
            value.gifts = ranked.compactMap { id in value.gifts.first { $0.identifier == id } } + value.gifts.filter { !ranked.contains($0.identifier) }
        }
    }

    func profileState(_ server: ProfileGiftsContext.State, accountId: EnginePeer.Id, peerId: EnginePeer.Id, collectionId: Int32?, senders: [Int64: EnginePeer] = [:]) -> ProfileGiftsContext.State {
        let value = self.appearance(accountId: accountId, targetPeerId: peerId)
        guard value.enabled else { return server }
        let owned = value.gifts.filter { $0.direction == .received && $0.isHistoryOnly != true && (collectionId == nil || ($0.collectionIds ?? []).contains(collectionId!)) }
        let local = owned.filter { accountId == peerId || $0.savedToProfile != false }
        var result = server
        let localSlugs = Set(owned.compactMap { item -> String? in
            if case let .unique(gift) = item.gift { return gift.slug }; return nil
        })
        let keepRemote: (ProfileGiftsContext.State.StarGift) -> Bool = { item in
            if case let .unique(gift) = item.gift { return !localSlugs.contains(gift.slug) }; return true
        }
        let gifts = local.map { $0.profileGift(accountId: peerId, sender: $0.counterpartyId.flatMap { senders[$0] }) }
        result.gifts = gifts + server.gifts.filter(keepRemote)
        let matching = gifts.filter { item in
            if item.savedToProfile && !server.filter.contains(.displayed) { return false }
            if !item.savedToProfile && !server.filter.contains(.hidden) { return false }
            let types: ProfileGiftsContext.Filters = [.unlimited, .limitedUpgradable, .limitedNonUpgradable, .unique]
            if server.filter.intersection(types).isEmpty { return true }
            switch item.gift {
            case .unique: return server.filter.contains(.unique)
            case let .generic(gift):
                return server.filter.contains(gift.availability == nil ? .unlimited : (gift.upgradeStars == nil ? .limitedNonUpgradable : .limitedUpgradable))
            }
        }
        let remote = server.filteredGifts.filter(keepRemote)
        result.filteredGifts = matching + remote
        result.count = max(0, (server.count ?? Int32(server.filteredGifts.count)) - Int32(server.filteredGifts.count - remote.count)) + Int32(matching.count)
        func arrange(_ items: [ProfileGiftsContext.State.StarGift]) -> [ProfileGiftsContext.State.StarGift] {
            let pinned = items.filter { $0.pinnedToTop }
            let other = items.filter { !$0.pinnedToTop }
            return pinned + (server.sorting == .date && collectionId == nil ? other.sorted { $0.date > $1.date } : other)
        }
        result.gifts = arrange(result.gifts)
        result.filteredGifts = arrange(result.filteredGifts)
        return result
    }

    func collection(accountId: EnginePeer.Id, targetPeerId: EnginePeer.Id? = nil, id: Int32) -> StarGiftCollection? {
        let value = self.appearance(accountId: accountId, targetPeerId: targetPeerId)
        guard let collection = value.collections?.first(where: { $0.id == id }) else { return nil }
        let gifts = value.gifts.filter { $0.direction == .received && $0.isHistoryOnly != true && (accountId == (targetPeerId ?? accountId) || $0.savedToProfile != false) && ($0.collectionIds ?? []).contains(id) }
        var icon: TelegramMediaFile?
        if let first = gifts.first {
            switch first.gift {
            case let .generic(gift): icon = gift.file
            case let .unique(gift):
                for attribute in gift.attributes { if case let .model(_, file, _, _) = attribute { icon = file; break } }
            }
        }
        return StarGiftCollection(id: id, title: collection.title, icon: icon, count: Int32(gifts.count), hash: 0)
    }

    func createCollection(accountId: EnginePeer.Id, targetPeerId: EnginePeer.Id? = nil, title: String, references: [StarGiftReference]) -> StarGiftCollection? {
        var id: Int32 = -1
        let target = targetPeerId ?? accountId
        self.update(accountId: accountId, targetPeerId: target) { value in
            let used = Set((value.collections ?? []).map { $0.id })
            while used.contains(id) && id > Int32.min { id -= 1 }
            value.collections = (value.collections ?? []) + [VisualGramGiftCollection(id: id, title: String(title.prefix(40)))]
            for index in value.gifts.indices where references.contains(value.gifts[index].reference(accountId: target)) {
                value.gifts[index].collectionIds = (value.gifts[index].collectionIds ?? []) + [id]
            }
        }
        return self.collection(accountId: accountId, targetPeerId: target, id: id)
    }

    func updateCollection(accountId: EnginePeer.Id, targetPeerId: EnginePeer.Id? = nil, id: Int32, actions: [ProfileGiftsCollectionsContext.UpdateAction]) {
        for action in actions {
            switch action {
            case let .updateTitle(title):
                self.update(accountId: accountId, targetPeerId: targetPeerId) { value in
                    if let index = value.collections?.firstIndex(where: { $0.id == id }) { value.collections?[index].title = String(title.prefix(40)) }
                }
            case let .addGifts(gifts):
                for gift in gifts {
                    _ = self.updateGift(accountId: accountId, reference: gift.reference) { local in
                        if !(local.collectionIds ?? []).contains(id) { local.collectionIds = (local.collectionIds ?? []) + [id] }
                    }
                }
            case let .removeGifts(references):
                for reference in references { _ = self.updateGift(accountId: accountId, reference: reference) { $0.collectionIds?.removeAll { $0 == id } } }
            case let .reorderGifts(references): self.reorderGifts(accountId: accountId, targetPeerId: targetPeerId, references: references)
            }
        }
    }

    func collectionsState(_ server: ProfileGiftsCollectionsContext.State, accountId: EnginePeer.Id, peerId: EnginePeer.Id) -> ProfileGiftsCollectionsContext.State {
        let value = self.appearance(accountId: accountId, targetPeerId: peerId)
        guard value.enabled else { return server }
        var result = server
        result.collections = (value.collections ?? []).compactMap { self.collection(accountId: accountId, targetPeerId: peerId, id: $0.id) } + server.collections.map { collection in
            let added = value.gifts.filter { $0.direction == .received && $0.isHistoryOnly != true && (accountId == peerId || $0.savedToProfile != false) && ($0.collectionIds ?? []).contains(collection.id) }.count
            return StarGiftCollection(id: collection.id, title: collection.title, icon: collection.icon, count: collection.count + Int32(added), hash: collection.hash)
        }
        return result
    }
}
