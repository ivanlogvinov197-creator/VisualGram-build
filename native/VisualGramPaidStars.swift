import Foundation
import Postbox

struct VisualGramPaidChatMessage: Codable, Equatable {
    let id: String
    let messageId: Int32
    let date: Int32
    let text: String
    let entities: [MessageTextEntity]
}

public enum VisualGramStarsSpendResult: Equatable {
    case saved
    case insufficientBalance
    case unavailable
}

public extension VisualGramLocalAppearance {
    func visualStarsBalance(accountId: EnginePeer.Id) -> Int64? {
        let profile = self.appearance(accountId: accountId)
        return profile.enabled ? profile.stars : nil
    }

    func sendVisualPaidMessages(
        accountId: EnginePeer.Id, peerId: EnginePeer.Id,
        messages: [(text: String, entities: [MessageTextEntity])], price: Int64, now: Int32
    ) -> VisualGramStarsSpendResult {
        guard peerId.namespace == Namespaces.Peer.CloudUser, peerId != accountId,
              !messages.isEmpty, price > 0,
              messages.allSatisfy({ !$0.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }) else {
            return .unavailable
        }
        let (total, overflow) = price.multipliedReportingOverflow(by: Int64(messages.count))
        guard !overflow else { return .unavailable }

        return self.spendVisualStars(accountId: accountId, peerId: peerId, amount: total, title: "Платное сообщение", now: now) { profile in
            var chats = profile.paidChatMessages ?? [:]
            let key = String(peerId.toInt64())
            let firstId = Int64(chats[key]?.last?.messageId ?? Int32.min) + 1
            // Keep these IDs below the existing synthetic gift and GRAM range.
            guard firstId + Int64(messages.count) <= -(1 << 30) else { return false }
            let stored = messages.enumerated().map { index, message in
                VisualGramPaidChatMessage(id: UUID().uuidString, messageId: Int32(firstId + Int64(index)), date: now, text: message.text, entities: message.entities)
            }
            chats[key, default: []].append(contentsOf: stored)
            profile.paidChatMessages = chats
            return true
        }
    }

    func addVisualPaidReaction(accountId: EnginePeer.Id, messageId: EngineMessage.Id, count: Int32, privacy: TelegramPaidReactionPrivacy = .default, now: Int32) -> VisualGramStarsSpendResult {
        guard messageId.peerId.namespace == Namespaces.Peer.CloudChannel,
              messageId.namespace == Namespaces.Message.Cloud, messageId.id > 0, count > 0 else {
            return .unavailable
        }
        return self.spendVisualStars(accountId: accountId, peerId: messageId.peerId, amount: Int64(count), title: "Звёздная реакция", now: now) { profile in
            let key = Self.visualPaidReactionKey(messageId)
            var reactions = profile.paidPostReactions ?? [:]
            let (updatedCount, overflow) = (reactions[key] ?? 0).addingReportingOverflow(count)
            guard !overflow else { return false }
            reactions[key] = updatedCount
            profile.paidPostReactions = reactions
            Self.saveVisualReactionPrivacy(profile: &profile, key: key, privacy: privacy)
            return true
        }
    }

    func visualReactionPrivacy(accountId: EnginePeer.Id, messageId: EngineMessage.Id) -> TelegramPaidReactionPrivacy {
        let value = self.appearance(accountId: accountId).paidReactionPrivacy?[Self.visualPaidReactionKey(messageId)] ?? 0
        if value == -1 { return .anonymous }
        if value == 0 { return .default }
        return .peer(EnginePeer.Id(value))
    }

    func setVisualReactionPrivacy(accountId: EnginePeer.Id, messageId: EngineMessage.Id, privacy: TelegramPaidReactionPrivacy) {
        self.update(accountId: accountId) { profile in
            guard profile.enabled, profile.paidPostReactions?[Self.visualPaidReactionKey(messageId)] != nil else { return }
            Self.saveVisualReactionPrivacy(profile: &profile, key: Self.visualPaidReactionKey(messageId), privacy: privacy)
        }
    }

    private static func saveVisualReactionPrivacy(profile: inout VisualGramAppearance, key: String, privacy: TelegramPaidReactionPrivacy) {
        let value: Int64
        switch privacy {
        case .default: value = 0
        case .anonymous: value = -1
        case let .peer(id): value = id.toInt64()
        }
        var settings = profile.paidReactionPrivacy ?? [:]
        settings[key] = value
        profile.paidReactionPrivacy = settings
    }

    func visualReactionTopPeers(accountId: EnginePeer.Id, messageId: EngineMessage.Id, existing: [ReactionsMessageAttribute.TopPeer]) -> [ReactionsMessageAttribute.TopPeer] {
        let count = self.visualPaidReactionCount(accountId: accountId, messageId: messageId)
        guard count > 0 else { return existing }
        let own = existing.first(where: { $0.isMy })
        let privacy = self.visualReactionPrivacy(accountId: accountId, messageId: messageId)
        let peerId: EnginePeer.Id?
        let anonymous: Bool
        switch privacy {
        case .default: peerId = accountId; anonymous = false
        case .anonymous: peerId = nil; anonymous = true
        case let .peer(id): peerId = id; anonymous = false
        }
        var peers = existing.filter { !$0.isMy }
        peers.append(.init(peerId: peerId, count: Int32(clamping: Int64(own?.count ?? 0) + Int64(count)), isTop: true, isMy: true, isAnonymous: anonymous))
        return peers.sorted { $0.count > $1.count }
    }

    func visualPaidReactionCount(accountId: EnginePeer.Id, messageId: EngineMessage.Id) -> Int32 {
        self.visualPaidReactions(accountId: accountId)[Self.visualPaidReactionKey(messageId)] ?? 0
    }

    func visualPaidReactions(accountId: EnginePeer.Id) -> [String: Int32] {
        let profile = self.appearance(accountId: accountId)
        guard profile.enabled, profile.stars != nil else { return [:] }
        return profile.paidPostReactions ?? [:]
    }

    static func visualPaidReactionKey(_ messageId: EngineMessage.Id) -> String {
        "\(messageId.peerId.toInt64()):\(messageId.namespace):\(messageId.id)"
    }

    static func displayingVisualPaidReaction(_ message: Message, count: Int32) -> Message {
        guard count > 0, !message.attributes.contains(where: { $0 is PendingStarsReactionsMessageAttribute }) else { return message }
        let previous = message.attributes.compactMap { $0 as? ReactionsMessageAttribute }.first
        var reactions = previous?.reactions ?? []
        if let index = reactions.firstIndex(where: { $0.value == .stars }) {
            reactions[index].chosenOrder = reactions[index].chosenOrder ?? 0
            reactions[index].count = Int32(clamping: Int64(reactions[index].count) + Int64(count))
        } else {
            reactions.insert(MessageReaction(value: .stars, count: count, chosenOrder: 0), at: 0)
        }
        let updated = ReactionsMessageAttribute(
            canViewList: previous?.canViewList ?? false,
            isTags: false,
            reactions: reactions,
            recentPeers: previous?.recentPeers ?? [],
            topPeers: previous?.topPeers ?? []
        )
        var attributes = message.attributes.filter { !($0 is ReactionsMessageAttribute) }
        attributes.append(updated)
        return message.withUpdatedAttributes(attributes).withUpdatedStableVersion(stableVersion: message.stableVersion &+ UInt32(count))
    }

    private func spendVisualStars(
        accountId: EnginePeer.Id, peerId: EnginePeer.Id, amount: Int64, title: String, now: Int32,
        _ apply: (inout VisualGramAppearance) -> Bool
    ) -> VisualGramStarsSpendResult {
        var result: VisualGramStarsSpendResult = .unavailable
        let persisted = self.updateValues(recordOperations: false) { values in
            let key = String(accountId.toInt64())
            guard var profile = values[key], profile.enabled, let balance = profile.stars else { return }
            guard balance >= amount else {
                result = .insufficientBalance
                return
            }
            guard apply(&profile) else { return }
            profile.stars = balance - amount
            Self.recordStarsTransaction(value: &profile, amount: -amount, kind: .purchase, peerId: peerId, gift: nil, title: title, now: now)
            values[key] = profile
            result = .saved
        }
        return persisted ? result : .unavailable
    }
}

public struct VisualGramStarsStatistics {
    public let balance: Int64
    public let received: Int64
    public let spent: Int64
    public let operations: Int
    public let incomingGraph: StatsGraph?

    public init?(appearance: VisualGramAppearance, now: Int32) {
        guard appearance.enabled, let balance = appearance.stars else { return nil }
        let entries = VisualGramBalanceHistory.stars.displayedEntries(in: appearance).filter { $0.date <= now }
        self.balance = balance
        self.operations = entries.count

        let dayInSeconds: Int64 = 86_400
        let lastDay = Int64(now) / dayInSeconds
        let firstDay = lastDay - 364
        var daily = Array(repeating: Int64(0), count: 365)
        var received: Int64 = 0
        var spent: Int64 = 0
        for entry in entries {
            if entry.amount > 0 {
                received = Self.add(received, entry.amount)
                let day = Int64(entry.date) / dayInSeconds
                if day >= firstDay {
                    daily[Int(day - firstDay)] = Self.add(daily[Int(day - firstDay)], entry.amount)
                }
            } else if entry.amount < 0 {
                spent = Self.add(spent, entry.amount == Int64.min ? Int64.max : -entry.amount)
            }
        }
        self.received = received
        self.spent = spent
        let dates = (firstDay ... lastDay).map { $0 * dayInSeconds * 1000 }
        let chart: [String: Any] = [
            "columns": [["x"] + dates.map { $0 as Any }, ["stars"] + daily.map { min($0, 1_000_000_000_000) as Any }],
            "types": ["x": "x", "stars": "bar"],
            "names": ["stars": "Поступления"],
            "colors": ["stars": "#E5A529"]
        ]
        if daily.contains(where: { $0 > 0 }),
           let data = try? JSONSerialization.data(withJSONObject: chart, options: [.sortedKeys]),
           let json = String(data: data, encoding: .utf8) {
            self.incomingGraph = .Loaded(token: nil, data: json)
        } else {
            self.incomingGraph = nil
        }
    }

    private static func add(_ lhs: Int64, _ rhs: Int64) -> Int64 {
        let (value, overflow) = lhs.addingReportingOverflow(rhs)
        return overflow ? Int64.max : value
    }
}
