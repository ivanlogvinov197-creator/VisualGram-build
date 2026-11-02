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
    static func orderedOwnedGifts(in value: VisualGramAppearance) -> [VisualGramGift] {
        let owned = value.gifts.filter { $0.direction == .received && $0.isHistoryOnly != true }
        var ranks: [String: Int] = [:]
        for (index, id) in (value.giftOrder ?? []).enumerated() where ranks[id] == nil { ranks[id] = index }
        return owned.enumerated().sorted { lhs, rhs in
            let a = lhs.element, b = rhs.element
            if (a.pinnedToTop == true) != (b.pinnedToTop == true) { return a.pinnedToTop == true }
            if value.giftOrder != nil {
                let first = ranks[a.identifier] ?? Int.max, second = ranks[b.identifier] ?? Int.max
                if first != second { return first < second }
            } else if a.pinnedToTop != true, a.date != b.date { return a.date > b.date }
            return lhs.offset < rhs.offset
        }.map { $0.element }
    }

    static func operationSnapshot(_ gift: VisualGramGift, kind: VisualGramGift.OperationKind? = nil, legacy: Bool = false) -> VisualGramGift {
        var result = gift
        result.localIdentifier = legacy ? "operation:" + gift.identifier : "operation:" + UUID().uuidString
        result.operationSourceId = gift.identifier
        if kind == .craft, let consumedAt = gift.consumedAt { result.date = consumedAt }
        result.operationKind = kind ?? (gift.isCrafted == true ? .craft : (gift.purchaseStars != nil || gift.purchaseGrams != nil ? .purchase : (gift.isTransferred == true ? .transfer : (gift.direction == .sent ? .sent : .received))))
        result.isHistoryOnly = true; result.resaleStars = nil; result.resaleGrams = nil
        return result
    }

    static func giftOperations(in value: VisualGramAppearance) -> [VisualGramGift] {
        return (value.giftOperationHistory ?? value.gifts.map { Self.operationSnapshot($0, legacy: true) }).sorted { $0.date > $1.date }
    }

    static func recordGiftOperations(previous: VisualGramAppearance?, value: inout VisualGramAppearance) {
        guard value.enabled || !value.gifts.isEmpty || value.giftOperationHistory != nil else { return }
        if value.giftOperationHistory == nil { value.giftOperationHistory = (previous?.gifts ?? []).map { Self.operationSnapshot($0, legacy: true) } }
        let old = previous?.gifts ?? []
        let ids = Set(old.map { $0.identifier })
        let added = value.gifts.filter { !ids.contains($0.identifier) }
        value.giftOperationHistory?.append(contentsOf: added.map { Self.operationSnapshot($0) })
        // Failed crafting has no newly inserted result. Record it once without
        // turning consumed inputs into active gifts or changing their model.
        let previousActive = Set(old.filter { $0.direction == .received && $0.isHistoryOnly != true }.map { $0.identifier })
        if added.isEmpty, let consumed = value.gifts.first(where: { current in
            current.direction == .received && current.isHistoryOnly == true && current.consumedAt != nil && previousActive.contains(current.identifier)
        }) { value.giftOperationHistory?.append(Self.operationSnapshot(consumed, kind: .craft)) }
    }

    @discardableResult
    func editGiftDetails(accountId: EnginePeer.Id, targetPeerId: EnginePeer.Id, identifier: String, history: Bool, counterpartyId: Int64?, date: Int32, text: String) -> Bool {
        var edited = false
        self.updateValues { values in
            let key = String(targetPeerId.toInt64())
            guard var value = values[key] else { return }
            var operations = Self.giftOperations(in: value)
            let record: VisualGramGift?
            if history { record = operations.first(where: { $0.identifier == identifier }) }
            else { record = value.gifts.first(where: { $0.identifier == identifier && $0.direction == .received && $0.isHistoryOnly != true }) }
            guard let original = record else { return }
            if original.direction == .sent && counterpartyId == nil { return }
            let sourceId = history ? original.operationSourceId : original.identifier
            let sourceIndex = value.gifts.firstIndex(where: { $0.identifier == sourceId && $0.date == original.date && $0.assetIdentifier == original.assetIdentifier })
            var mirror: (String, Int, VisualGramGift)?
            if sourceIndex != nil, let previousPeer = original.counterpartyId, previousPeer != targetPeerId.toInt64(), let other = values[String(previousPeer)], let index = other.gifts.firstIndex(where: { $0.assetIdentifier == original.assetIdentifier && $0.date == original.date && $0.counterpartyId == targetPeerId.toInt64() && $0.direction != original.direction }) {
                mirror = (String(previousPeer), index, other.gifts[index])
            }
            if let mirror, let newPeer = counterpartyId, newPeer != original.counterpartyId, mirror.2.direction == .received && mirror.2.isHistoryOnly != true,
               values[String(newPeer)]?.gifts.contains(where: { $0.assetIdentifier == original.assetIdentifier && $0.direction == .received && $0.isHistoryOnly != true && $0.identifier != mirror.2.identifier }) == true { return }
            if let index = sourceIndex {
                value.gifts[index].counterpartyId = counterpartyId; value.gifts[index].date = date; value.gifts[index].text = text; value.gifts[index].textEntities = nil
                if mirror != nil, original.direction == .sent, counterpartyId == targetPeerId.toInt64() {
                    value.gifts[index].direction = .received; value.gifts[index].isHistoryOnly = false
                }
            }
            let operationIndex = history ? operations.firstIndex(where: { $0.identifier == identifier }) : operations.lastIndex(where: { $0.operationSourceId == identifier })
            if let index = operationIndex { operations[index].counterpartyId = counterpartyId; operations[index].date = date; operations[index].text = text; operations[index].textEntities = nil }
            value.giftOperationHistory = operations
            values[key] = value
            if let (oldKey, index, previous) = mirror {
                var other = values[oldKey] ?? VisualGramAppearance()
                var mirrored = previous; mirrored.counterpartyId = targetPeerId.toInt64(); mirrored.date = date; mirrored.text = text; mirrored.textEntities = nil
                if let newPeer = counterpartyId, String(newPeer) == oldKey {
                    other.gifts[index] = mirrored; values[oldKey] = other
                } else {
                    Self.removeGiftData(from: &other, identifiers: [previous.identifier]); values[oldKey] = other
                    if let newPeer = counterpartyId, newPeer != targetPeerId.toInt64() {
                        var target = values[String(newPeer)] ?? VisualGramAppearance(); target.enabled = true
                        Self.insertGift(mirrored, into: &target); values[String(newPeer)] = target
                    }
                }
                if counterpartyId == original.counterpartyId, var other = values[oldKey] {
                    var ledger = Self.giftOperations(in: other)
                    if let index = ledger.lastIndex(where: { $0.operationSourceId == previous.identifier && $0.date == previous.date }) { ledger[index].date = date; ledger[index].text = text; ledger[index].textEntities = nil }
                    other.giftOperationHistory = ledger; values[oldKey] = other
                }
            }
            edited = true
        }
        return edited
    }

    @discardableResult
    func saveGiftOrder(accountId: EnginePeer.Id, targetPeerId: EnginePeer.Id, identifiers: [String]) -> Bool {
        var saved = false
        self.update(accountId: accountId, targetPeerId: targetPeerId) { value in
            let owned = value.gifts.filter { $0.direction == .received && $0.isHistoryOnly != true }
            guard identifiers.count == owned.count, Set(identifiers).count == identifiers.count,
                  Set(identifiers) == Set(owned.map { $0.identifier }) else { return }
            let byId = Dictionary(uniqueKeysWithValues: owned.map { ($0.identifier, $0) })
            // Telegram always renders pinned gifts first. Preserve that invariant
            // in storage as well, so the editor agrees with the profile.
            let ordered = identifiers.compactMap { byId[$0] }
            let normalized = ordered.filter { $0.pinnedToTop == true } + ordered.filter { $0.pinnedToTop != true }
            value.giftOrder = normalized.map { $0.identifier }
            var index = 0
            value.gifts = value.gifts.map { gift in
                guard gift.direction == .received && gift.isHistoryOnly != true else { return gift }
                defer { index += 1 }
                return normalized[index]
            }
            saved = true
        }
        return saved
    }
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

    func editScheduledGift(id: String, gift: VisualGramGift, deliveryDate: Int32) {
        self.updateValues { values in
            for key in Array(values.keys) {
                if let index = values[key]?.scheduledGifts?.firstIndex(where: { $0.id == id && $0.gift.identifier == gift.identifier }) {
                    values[key]?.scheduledGifts?[index].gift = gift
                    values[key]?.scheduledGifts?[index].deliveryDate = deliveryDate
                }
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
        self.updateValues { values in
            for gift in gifts { Self.insertDeliveredGift(gift, targetPeerId: targetPeerId, values: &values) }
        }
    }

    static func insertDeliveredGift(_ gift: VisualGramGift, targetPeerId: EnginePeer.Id, values: inout [String: VisualGramAppearance]) {
        let key = String(targetPeerId.toInt64())
        var target = values[key] ?? VisualGramAppearance(); target.enabled = true
        if gift.direction == .sent, let recipient = gift.counterpartyId {
            var incoming = gift; incoming.direction = .received; incoming.counterpartyId = targetPeerId.toInt64(); incoming.isHistoryOnly = false
            if recipient == targetPeerId.toInt64() { Self.insertGift(incoming, into: &target) }
            else {
                var outgoing = gift; outgoing.isHistoryOnly = true; Self.insertGift(outgoing, into: &target)
                let recipientKey = String(recipient)
                var owner = values[recipientKey] ?? VisualGramAppearance(); owner.enabled = true
                Self.insertGift(incoming, into: &owner); values[recipientKey] = owner
            }
        } else { Self.insertGift(gift, into: &target) }
        values[key] = target
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
            value.giftOrder = value.gifts.map { $0.identifier }
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
                Self.insertDeliveredGift(gift, targetPeerId: EnginePeer.Id(pending.targetPeerId), values: &values)
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
    func upgradeLocalGift(accountId: EnginePeer.Id, reference: StarGiftReference?, preview: StarGiftUpgradePreview, keepOriginalInfo: Bool, template: StarGift.UniqueGift? = nil) -> ProfileGiftsContext.State.StarGift? {
        guard self.canManageLocalGift(accountId: accountId, reference: reference),
              let local = self.localGift(accountId: accountId, reference: reference), local.direction == .received,
              case let .generic(generic) = local.gift, case let .message(messageId) = reference else { return nil }
        guard let unique = Self.makeUpgradedGift(generic, preview: preview, ownerId: messageId.peerId, template: template) else { return nil }
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

    static func makeUpgradedGift(_ generic: StarGift.Gift, preview: StarGiftUpgradePreview, ownerId: EnginePeer.Id, template: StarGift.UniqueGift? = nil) -> StarGift.UniqueGift? {
        guard template == nil || template?.giftId == generic.id else { return nil }
        guard generic.upgradeStars != nil,
              let model = preview.attributes.filter({ if case let .model(_, _, _, crafted) = $0 { return !crafted }; return false }).randomElement(),
              let pattern = preview.attributes.filter({ $0.attributeType == .pattern }).randomElement(),
              let backdrop = preview.attributes.filter({ $0.attributeType == .backdrop }).randomElement() else { return nil }
        let total = max(1, template?.availability.total ?? generic.availability?.total ?? 100000)
        let number = template?.number ?? Int32.random(in: 1 ... total)
        let title = template?.title ?? generic.title ?? "Gift"
        let prefix = title.filter { $0.isASCII && ($0.isLetter || $0.isNumber) }
        return StarGift.UniqueGift(id: -Int64.random(in: 1 ... Int64.max), giftId: generic.id,
            title: title, number: number,
            slug: template?.slug ?? "\(prefix.isEmpty ? "Gift" : prefix)-\(number)", owner: .peerId(ownerId), attributes: template.map { $0.attributes.filter { $0.attributeType != .originalInfo } } ?? [model, pattern, backdrop],
            availability: .init(issued: 1, total: total), giftAddress: nil, resellAmounts: nil,
            resellForTonOnly: false, releasedBy: generic.releasedBy, valueAmount: nil, valueCurrency: nil,
            valueUsdAmount: nil, flags: [], themePeerId: nil, peerColor: nil, hostPeerId: nil,
            minOfferStars: nil, craftChancePermille: template?.craftChancePermille)
    }

    @discardableResult
    func updateGift(accountId: EnginePeer.Id, reference: StarGiftReference?, change: (inout VisualGramGift) -> Void) -> Bool {
        guard self.canManageLocalGift(accountId: accountId, reference: reference), let gift = self.localGift(accountId: accountId, reference: reference), case let .message(id) = reference else { return false }
        self.update(accountId: accountId, targetPeerId: id.peerId) { value in
            if let index = value.gifts.firstIndex(where: { $0.identifier == gift.identifier }) { change(&value.gifts[index]) }
        }
        return true
    }

    func removeLocalGifts(accountId: EnginePeer.Id, targetPeerId: EnginePeer.Id? = nil, identifiers: Set<String>) {
        self.update(accountId: accountId, targetPeerId: targetPeerId) { value in Self.removeGiftData(from: &value, identifiers: identifiers) }
    }

    static func removeGiftData(from value: inout VisualGramAppearance, identifiers: Set<String>) {
            if case let .starGift(id, _, _, _, _, _, _, _, _) = value.emojiStatus?.content,
               value.gifts.contains(where: { local in
                   guard identifiers.contains(local.identifier), local.direction == .received, local.isHistoryOnly != true,
                         case let .unique(gift) = local.gift else { return false }
                   return gift.id == id
               }) {
                value.overridesEmojiStatus = true
                value.emojiStatus = nil
            }
            value.gifts.removeAll { identifiers.contains($0.identifier) }
            value.giftOrder?.removeAll { identifiers.contains($0) }
            value.gramCardGiftIds?.removeAll { identifiers.contains($0) }
            value.gramCardPlacements = value.gramCardPlacements?.filter { !identifiers.contains($0.key) }
            if let id = value.gramCardBackgroundId, identifiers.contains(id) { value.gramCardBackgroundId = nil }
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
            if let order = value.giftOrder, server.sorting == .date, collectionId == nil {
                var ranks: [StarGiftReference: Int] = [:]
                for (index, id) in order.enumerated() { if let gift = value.gifts.first(where: { $0.identifier == id }) { ranks[gift.reference(accountId: peerId)] = index } }
                return pinned + other.enumerated().sorted { lhs, rhs in
                    let a = lhs.element.reference.flatMap { ranks[$0] } ?? Int.max
                    let b = rhs.element.reference.flatMap { ranks[$0] } ?? Int.max
                    return a == b ? lhs.offset < rhs.offset : a < b
                }.map { $0.element }
            }
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
