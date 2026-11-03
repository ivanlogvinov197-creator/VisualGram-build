import Foundation

public enum VisualGramGiftUndoResult { case success, notFound, legacyUnavailable, dependentOperation, balanceChanged, invalidData }

private struct VisualGramGiftChange: Codable {
    var profile: String
    var before: VisualGramGift?
    var beforeIndex: Int
    var after: VisualGramGift?
}

private struct VisualGramGiftStyle: Codable {
    var order: [String]?
    var stickers: [String]?
    var background: String?
    var placements: [String: VisualGramGift.CardPlacement]?
    var overridesStatus: Bool
    var status: PeerEmojiStatus?
    init(_ value: VisualGramAppearance) {
        self.order = value.giftOrder; self.stickers = value.gramCardGiftIds
        self.background = value.gramCardBackgroundId; self.placements = value.gramCardPlacements
        self.overridesStatus = value.overridesEmojiStatus; self.status = value.emojiStatus
    }
    func restore(previous: Self, current: Self, value: inout VisualGramAppearance) {
        if current.order == self.order { value.giftOrder = previous.order }
        if current.stickers == self.stickers { value.gramCardGiftIds = previous.stickers }
        if current.background == self.background { value.gramCardBackgroundId = previous.background }
        if current.placements == self.placements { value.gramCardPlacements = previous.placements }
        if current.status == self.status && current.overridesStatus == self.overridesStatus {
            value.emojiStatus = previous.status; value.overridesEmojiStatus = previous.overridesStatus
        }
    }
}

private struct VisualGramGiftProfileUndo: Codable {
    var profile: String
    var starsBefore: Int64?
    var starsAfter: Int64?
    var gramsBefore: Int64?
    var gramsAfter: Int64?
    var starsEntries: [String]
    var gramsEntries: [String]
    var countsBefore: [String: Int32]?
    var countsAfter: [String: Int32]?
    var styleBefore: VisualGramGiftStyle
    var styleAfter: VisualGramGiftStyle
}

private struct VisualGramGiftUndo: Codable {
    var version = 1
    var event: String
    var gifts: [VisualGramGiftChange]
    var profiles: [VisualGramGiftProfileUndo]
}

public extension VisualGramLocalAppearance {
    internal static func editGiftOperationNarrative(_ original: VisualGramGift, profile: Int64, counterparty: Int64?, date: Int32, text: String, values: inout [String: VisualGramAppearance]) {
        guard let event = original.operationEventId else { return }
        var sender = original.operationSenderId, recipient = original.operationRecipientId
        if original.operationKind != .craft && original.operationKind != .upgrade {
            if original.direction == .sent { recipient = counterparty } else { sender = counterparty }
        }
        let oldParticipants = Set([original.operationSenderId, original.operationRecipientId].compactMap { $0 }.map(String.init))
        var participants = Set([sender, recipient].compactMap { $0 }.map(String.init)); participants.insert(String(profile))
        for key in Set(values.keys).union(participants) {
            guard participants.contains(key) || values[key]?.giftOperationHistory?.contains(where: { $0.operationEventId == event }) == true else { continue }
            var value = values[key] ?? VisualGramAppearance()
            var history = value.giftOperationHistory ?? []
            if oldParticipants.contains(key) && !participants.contains(key) { history.removeAll { $0.operationEventId == event } }
            else {
                var record = history.first(where: { $0.operationEventId == event }) ?? original
                record.localIdentifier = "operation:" + event + ":" + key
                record.operationSenderId = sender; record.operationRecipientId = recipient
                record.date = date; record.text = text; record.textEntities = nil
                record.direction = Int64(key) == sender && sender != recipient ? .sent : .received
                record.counterpartyId = record.direction == .sent ? recipient : (sender == recipient ? nil : sender)
                if record.operationKind == .sent || record.operationKind == .received { record.operationKind = record.direction == .sent ? .sent : .received; record.operationEventKind = record.operationKind?.rawValue }
                if let index = history.firstIndex(where: { $0.operationEventId == event }) { history[index] = record } else { history.append(record) }
            }
            value.giftOperationHistory = history; values[key] = value
        }
    }

    // Compare the transaction itself. Asset provenance (crafted/bought) never decides a later event's kind.
    static func recordGiftOperations(previous: [String: VisualGramAppearance], values: inout [String: VisualGramAppearance], now: Int32 = Int32(clamping: Int64(Date().timeIntervalSince1970))) {
        let after = values
        let keys = Set(previous.keys).union(after.keys).sorted()
        var changes: [VisualGramGiftChange] = []
        for key in keys {
            let old = previous[key]?.gifts ?? [], new = after[key]?.gifts ?? []
            for id in Set(old.map { $0.identifier }).union(new.map { $0.identifier }).sorted() {
                let oldIndex = old.firstIndex { $0.identifier == id }
                let before = oldIndex.map { old[$0] }
                let current = new.first { $0.identifier == id }
                if before != current { changes.append(.init(profile: key, before: before, beforeIndex: oldIndex ?? 0, after: current)) }
            }
            if var value = values[key], value.giftOperationHistory == nil {
                value.giftOperationHistory = old.map { Self.operationSnapshot($0, legacy: true) }
                values[key] = value
            }
        }
        guard !changes.isEmpty else { return }
        let active: (VisualGramGift?) -> Bool = { $0?.direction == .received && $0?.isHistoryOnly != true }
        let consumed = changes.filter { active($0.before) && $0.after?.isHistoryOnly == true && $0.after?.consumedAt != nil && $0.after?.consumedAt != $0.before?.consumedAt }
        if let first = consumed.first {
            let result = changes.first { $0.profile == first.profile && $0.before == nil && active($0.after) && $0.after?.isCrafted == true }?.after
            let inputs = consumed.compactMap { $0.before?.gift }
            Self.appendGiftEvent(kind: .craft, sender: Int64(first.profile), recipient: Int64(first.profile), date: first.after?.consumedAt ?? now, inputs: inputs, result: result, succeeded: result != nil, changes: changes, previous: previous, values: &values)
            return
        }
        // The new payment ledger entry is evidence of this purchase; old purchase flags are not.
        for key in keys {
            let oldIds = Set((previous[key]?.starsHistory ?? []).map { $0.id } + (previous[key]?.gramHistory ?? []).map { $0.id })
            let added = (after[key]?.starsHistory ?? []) + (after[key]?.gramHistory ?? [])
            if let payment = added.first(where: { !oldIds.contains($0.id) && $0.kind == .purchase && $0.amount < 0 }) {
                let received = changes.first { active($0.after) && $0.before == nil }
                Self.appendGiftEvent(kind: .purchase, sender: Int64(key), recipient: received.flatMap { Int64($0.profile) }, date: payment.date, inputs: [], result: received?.after, succeeded: true, changes: changes, previous: previous, values: &values)
                return
            }
        }
        // A transfer moves the existing local instance between owners, including crafted NFTs.
        for change in changes where active(change.before) && !active(change.after) {
            guard let old = change.before,
                  let incoming = changes.first(where: { $0.profile != change.profile && active($0.after) && $0.after?.identifier == old.identifier }) else { continue }
            Self.appendGiftEvent(kind: .transfer, sender: Int64(change.profile), recipient: Int64(incoming.profile), date: incoming.after?.date ?? now, inputs: [old.gift], result: incoming.after, succeeded: true, changes: changes, previous: previous, values: &values)
            return
        }
        for change in changes {
            if case .generic = change.before?.gift, case .unique = change.after?.gift {
                Self.appendGiftEvent(kind: .upgrade, sender: Int64(change.profile), recipient: Int64(change.profile), date: now, inputs: change.before.map { [$0.gift] } ?? [], result: change.after, succeeded: true, changes: [change], previous: previous, values: &values)
            }
        }
        let previousIds = Set(previous.values.flatMap { $0.gifts.map { $0.identifier } })
        var recorded = Set<String>()
        for change in changes where change.before == nil && active(change.after) {
            guard let gift = change.after, !previousIds.contains(gift.identifier), recorded.insert(gift.identifier).inserted else { continue }
            let related = changes.filter { $0.after?.identifier == gift.identifier || $0.before?.identifier == gift.identifier }
            Self.appendGiftEvent(kind: .received, sender: gift.counterpartyId, recipient: Int64(change.profile), date: gift.date, inputs: [], result: gift, succeeded: true, changes: related, previous: previous, values: &values)
        }
    }

    private static func appendGiftEvent(kind: VisualGramGift.OperationKind, sender: Int64?, recipient: Int64?, date: Int32, inputs: [StarGift], result: VisualGramGift?, succeeded: Bool, changes: [VisualGramGiftChange], previous: [String: VisualGramAppearance], values: inout [String: VisualGramAppearance]) {
        guard let representative = result ?? changes.compactMap({ $0.before }).first else { return }
        let event = UUID().uuidString
        var stamped = changes
        for index in stamped.indices { stamped[index].after?.lifecycleEventId = event }
        var profiles: [VisualGramGiftProfileUndo] = []
        for key in Set(changes.map { $0.profile }).sorted() {
            let before = previous[key] ?? VisualGramAppearance(), after = values[key] ?? VisualGramAppearance()
            let oldStars = Set((before.starsHistory ?? []).map { $0.id }), oldGrams = Set((before.gramHistory ?? []).map { $0.id })
            profiles.append(.init(profile: key, starsBefore: before.stars, starsAfter: after.stars, gramsBefore: before.grams, gramsAfter: after.grams, starsEntries: (after.starsHistory ?? []).filter { !oldStars.contains($0.id) }.map { $0.id }, gramsEntries: (after.gramHistory ?? []).filter { !oldGrams.contains($0.id) }.map { $0.id }, countsBefore: before.giftPurchaseCounts, countsAfter: after.giftPurchaseCounts, styleBefore: .init(before), styleAfter: .init(after)))
        }
        let undo = VisualGramGiftUndo(event: event, gifts: stamped, profiles: profiles)
        let data = try? JSONEncoder().encode(undo)
        for change in stamped {
            if let current = change.after, let index = values[change.profile]?.gifts.firstIndex(where: { $0.identifier == current.identifier }) {
                values[change.profile]?.gifts[index].lifecycleEventId = event
            }
        }
        var participants = Set(changes.map { $0.profile })
        if let sender { participants.insert(String(sender)) }
        if let recipient { participants.insert(String(recipient)) }
        for key in participants.sorted() {
            var value = values[key] ?? VisualGramAppearance()
            var record = Self.operationSnapshot(representative, kind: kind)
            record.localIdentifier = "operation:" + event + ":" + key
            record.operationEventId = event; record.operationEventKind = kind.rawValue; record.operationUndo = data
            record.operationSenderId = sender; record.operationRecipientId = recipient
            record.operationInputs = inputs; record.operationResult = result?.gift; record.operationSucceeded = succeeded
            record.date = date
            record.direction = Int64(key) == sender && sender != recipient ? .sent : .received
            record.counterpartyId = record.direction == .sent ? recipient : (sender == recipient ? nil : sender)
            if kind == .received {
                record.operationKind = record.direction == .sent ? .sent : .received
                record.operationEventKind = record.operationKind?.rawValue
            }
            var history = value.giftOperationHistory ?? []
            history.append(record); value.giftOperationHistory = history; values[key] = value
        }
    }

    @discardableResult
    func cancelGiftOperation(accountId: EnginePeer.Id, targetPeerId: EnginePeer.Id, identifier: String) -> VisualGramGiftUndoResult {
        var result: VisualGramGiftUndoResult = .notFound
        self.updateValues(recordOperations: false) { values in
            guard let record = values[String(targetPeerId.toInt64())]?.giftOperationHistory?.first(where: { $0.identifier == identifier }) else { return }
            guard let data = record.operationUndo, let event = record.operationEventId else { result = .legacyUnavailable; return }
            guard let undo = try? JSONDecoder().decode(VisualGramGiftUndo.self, from: data), undo.version == 1, undo.event == event else { result = .invalidData; return }
            var restored = values
            result = Self.restoreGiftOperation(undo, values: &restored)
            if case .success = result {
                for key in Array(restored.keys) { restored[key]?.giftOperationHistory?.removeAll { $0.operationEventId == event } }
                values = restored
            }
        }
        return result
    }

    private static func restoreGiftOperation(_ undo: VisualGramGiftUndo, values: inout [String: VisualGramAppearance]) -> VisualGramGiftUndoResult {
        // Compare lifecycle tokens, not cosmetic fields. Later transfers/upgrades/crafts must be undone first.
        let expected = undo.gifts.compactMap { $0.after }
        let ids = Set(expected.map { $0.identifier })
        var expectedCounts: [String: Int] = [:]
        for gift in expected { expectedCounts[gift.identifier, default: 0] += 1 }
        let current = values.values.flatMap { $0.gifts }.filter { ids.contains($0.identifier) && $0.lifecycleEventId == undo.event }
        var currentCounts: [String: Int] = [:]
        for gift in current { currentCounts[gift.identifier, default: 0] += 1 }
        guard currentCounts == expectedCounts else { return .dependentOperation }
        // Validate/refund against current balances so unrelated later transactions remain intact.
        for patch in undo.profiles {
            guard var value = values[patch.profile] else { return .dependentOperation }
            func inverse(_ old: Int64?, _ after: Int64?, _ current: Int64?) -> (Bool, Int64?) {
                guard old != after else { return (true, current) }
                guard let current else { return (false, nil) }
                let (delta, overflow) = (after ?? 0).subtractingReportingOverflow(old ?? 0)
                let (restored, inverseOverflow) = current.subtractingReportingOverflow(delta)
                guard !overflow, !inverseOverflow, restored >= 0 else { return (false, nil) }
                return (true, old == nil && current == after ? nil : restored)
            }
            let stars = inverse(patch.starsBefore, patch.starsAfter, value.stars), grams = inverse(patch.gramsBefore, patch.gramsAfter, value.grams)
            guard stars.0, grams.0 else { return .balanceChanged }
            value.stars = stars.1; value.grams = grams.1
            let starIds = Set(patch.starsEntries), gramIds = Set(patch.gramsEntries)
            value.starsHistory?.removeAll { starIds.contains($0.id) }; value.gramHistory?.removeAll { gramIds.contains($0.id) }
            for key in Set((patch.countsBefore ?? [:]).keys).union((patch.countsAfter ?? [:]).keys) {
                let before = patch.countsBefore?[key] ?? 0, after = patch.countsAfter?[key] ?? 0
                guard before != after else { continue }
                let restored = Int64(value.giftPurchaseCounts?[key] ?? 0) - (Int64(after) - Int64(before))
                guard restored >= 0, restored <= Int64(Int32.max) else { return .balanceChanged }
                if restored == 0 && patch.countsBefore?[key] == nil { value.giftPurchaseCounts?.removeValue(forKey: key) }
                else { value.giftPurchaseCounts = value.giftPurchaseCounts ?? [:]; value.giftPurchaseCounts?[key] = Int32(restored) }
            }
            values[patch.profile] = value
        }
        var styles: [String: VisualGramGiftStyle] = [:]
        for key in Array(values.keys) {
            guard var value = values[key] else { continue }
            styles[key] = .init(value)
            let removed = Set(value.gifts.filter { ids.contains($0.identifier) && $0.lifecycleEventId == undo.event }.map { $0.identifier })
            Self.removeGiftData(from: &value, identifiers: removed)
            values[key] = value
        }
        for change in undo.gifts.sorted(by: { $0.beforeIndex < $1.beforeIndex }) {
            guard let before = change.before else { continue }
            var value = values[change.profile] ?? VisualGramAppearance()
            guard !value.gifts.contains(where: { $0.identifier == before.identifier }) else { return .dependentOperation }
            value.gifts.insert(before, at: min(change.beforeIndex, value.gifts.count))
            values[change.profile] = value
        }
        for patch in undo.profiles {
            guard var value = values[patch.profile], let current = styles[patch.profile] else { continue }
            patch.styleAfter.restore(previous: patch.styleBefore, current: current, value: &value)
            values[patch.profile] = value
        }
        return .success
    }
}
