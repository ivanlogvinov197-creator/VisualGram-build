import Foundation
import Postbox

public struct VisualGramChannelProperties: Codable, Equatable {
    public var title: String
    public var about: String
    public var username: String?
    public var subscriberCount: Int32?
    public var verified: Bool
    public var signaturesEnabled: Bool
    public var showAuthors: Bool
    public var color: Int32?

    public init(
        title: String,
        about: String = "",
        username: String? = nil,
        subscriberCount: Int32? = nil,
        verified: Bool = false,
        signaturesEnabled: Bool = false,
        showAuthors: Bool = false,
        color: Int32? = nil
    ) {
        self.title = title
        self.about = about
        self.username = username
        self.subscriberCount = subscriberCount
        self.verified = verified
        self.signaturesEnabled = signaturesEnabled
        self.showAuthors = showAuthors
        self.color = color
    }

    fileprivate func validated() -> Self? {
        var result = self
        guard !self.title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              (self.subscriberCount ?? 0) >= 0 else { return nil }
        if var name = self.username?.trimmingCharacters(in: .whitespacesAndNewlines) {
            if name.hasPrefix("@") { name.removeFirst() }
            guard name.utf8.count <= 32, name.utf8.allSatisfy({
                (48...57).contains($0) || (65...90).contains($0) || (97...122).contains($0) || $0 == 95
            }) else { return nil }
            result.username = name.isEmpty ? nil : name
        }
        if !self.signaturesEnabled { result.showAuthors = false }
        return result
    }
}

public struct VisualGramChannelPost: Codable, Equatable, Identifiable {
    public let id: UUID
    public internal(set) var text: String
    public let date: Int32
}

public struct VisualGramChannelRecord: Codable, Equatable, Identifiable {
    public let sourcePeerId: Int64
    public internal(set) var isCopied: Bool
    public internal(set) var properties: VisualGramChannelProperties
    public internal(set) var subscriberCountOverride: Int32?
    public internal(set) var posts: [VisualGramChannelPost]
    fileprivate var sourceProperties: VisualGramChannelProperties?

    public var id: Int64 { self.sourcePeerId }
}

/// Channel copies live in the visual-appearance vault for the currently selected account.
public extension VisualGramLocalAppearance {
    func visualChannel(accountId: EnginePeer.Id, sourcePeerId: EnginePeer.Id) -> VisualGramChannelRecord? {
        guard sourcePeerId.namespace == Namespaces.Peer.CloudChannel else { return nil }
        return self.appearance(accountId: accountId).visualChannels?[String(sourcePeerId.toInt64())]
    }

    func visualChannels(accountId: EnginePeer.Id) -> [VisualGramChannelRecord] {
        self.appearance(accountId: accountId).visualChannels?.values.sorted { first, second in
            let order = first.properties.title.localizedStandardCompare(second.properties.title)
            return order == .orderedSame ? first.sourcePeerId < second.sourcePeerId : order == .orderedAscending
        } ?? []
    }

    /// A nil count clears the override. A count-only record has no local publishing or editing privileges.
    func setVisualChannelSubscriberCount(
        accountId: EnginePeer.Id, sourcePeerId: EnginePeer.Id, count: Int32?, initial: VisualGramChannelProperties
    ) -> Bool {
        guard (count ?? 0) >= 0 else { return false }
        return self.changeVisualChannel(accountId: accountId, sourcePeerId: sourcePeerId) { record in
            if var existing = record, existing.isCopied || count != nil {
                let displayedCount = count ?? initial.subscriberCount
                guard (displayedCount ?? 0) >= 0 else { return false }
                existing.subscriberCountOverride = count
                existing.properties.subscriberCount = displayedCount
                record = existing
            } else if let count {
                var properties = initial
                properties.subscriberCount = count
                guard let validated = properties.validated() else { return false }
                record = .init(sourcePeerId: sourcePeerId.toInt64(), isCopied: false, properties: validated,
                               subscriberCountOverride: count, posts: [])
            } else {
                record = nil
            }
            return true
        }
    }

    /// Re-copying an existing copy leaves its locally edited properties and post history intact.
    func copyVisualChannel(
        accountId: EnginePeer.Id, sourcePeerId: EnginePeer.Id, initial: VisualGramChannelProperties
    ) -> Bool {
        self.changeVisualChannel(accountId: accountId, sourcePeerId: sourcePeerId) { record in
            if record?.isCopied == true { return true }
            guard let source = initial.validated() else { return false }
            let override = record?.subscriberCountOverride
            var properties = source
            if let override { properties.subscriberCount = override }
            record = .init(sourcePeerId: sourcePeerId.toInt64(), isCopied: true, properties: properties,
                           subscriberCountOverride: override, posts: [], sourceProperties: source)
            return true
        }
    }

    func removeVisualChannelCopy(accountId: EnginePeer.Id, sourcePeerId: EnginePeer.Id) -> Bool {
        self.changeVisualChannel(accountId: accountId, sourcePeerId: sourcePeerId) { record in
            guard let existing = record, existing.isCopied else { return false }
            if let count = existing.subscriberCountOverride {
                var properties = existing.sourceProperties ?? .init(title: String(existing.sourcePeerId))
                properties.subscriberCount = count
                record = .init(sourcePeerId: existing.sourcePeerId, isCopied: false, properties: properties,
                               subscriberCountOverride: count, posts: [])
            } else {
                record = nil
            }
            return true
        }
    }

    func updateVisualChannelProperties(
        accountId: EnginePeer.Id, sourcePeerId: EnginePeer.Id, properties: VisualGramChannelProperties
    ) -> Bool {
        self.updateVisualChannelProperties(accountId: accountId, sourcePeerId: sourcePeerId) { $0 = properties }
    }

    func updateVisualChannelProperties(
        accountId: EnginePeer.Id, sourcePeerId: EnginePeer.Id, _ transform: (inout VisualGramChannelProperties) -> Void
    ) -> Bool {
        self.changeCopiedVisualChannel(accountId: accountId, sourcePeerId: sourcePeerId) { record in
            var properties = record.properties
            transform(&properties)
            guard let validated = properties.validated() else { return false }
            if validated.subscriberCount != record.properties.subscriberCount {
                record.subscriberCountOverride = validated.subscriberCount
            }
            record.properties = validated
            return true
        }
    }

    func addVisualChannelPost(accountId: EnginePeer.Id, sourcePeerId: EnginePeer.Id, text: String, now: Int32) -> Bool {
        guard Self.validVisualChannelPostText(text) else { return false }
        return self.changeCopiedVisualChannel(accountId: accountId, sourcePeerId: sourcePeerId) { record in
            record.posts.append(.init(id: UUID(), text: text, date: now))
            return true
        }
    }

    func editVisualChannelPost(accountId: EnginePeer.Id, sourcePeerId: EnginePeer.Id, postId: UUID, text: String) -> Bool {
        guard Self.validVisualChannelPostText(text) else { return false }
        return self.changeCopiedVisualChannel(accountId: accountId, sourcePeerId: sourcePeerId) { record in
            guard let index = record.posts.firstIndex(where: { $0.id == postId }) else { return false }
            record.posts[index].text = text
            return true
        }
    }

    func removeVisualChannelPost(accountId: EnginePeer.Id, sourcePeerId: EnginePeer.Id, postId: UUID) -> Bool {
        self.changeCopiedVisualChannel(accountId: accountId, sourcePeerId: sourcePeerId) { record in
            guard let index = record.posts.firstIndex(where: { $0.id == postId }) else { return false }
            record.posts.remove(at: index)
            return true
        }
    }

    private static func validVisualChannelPostText(_ text: String) -> Bool {
        text.utf16.count <= 4096 && !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }

    private func changeCopiedVisualChannel(
        accountId: EnginePeer.Id, sourcePeerId: EnginePeer.Id, change: (inout VisualGramChannelRecord) -> Bool
    ) -> Bool {
        self.changeVisualChannel(accountId: accountId, sourcePeerId: sourcePeerId) { record in
            guard var existing = record, existing.isCopied, change(&existing) else { return false }
            record = existing
            return true
        }
    }

    private func changeVisualChannel(
        accountId: EnginePeer.Id, sourcePeerId: EnginePeer.Id, change: (inout VisualGramChannelRecord?) -> Bool
    ) -> Bool {
        guard sourcePeerId.namespace == Namespaces.Peer.CloudChannel else { return false }
        let accountKey = String(accountId.toInt64())
        let channelKey = String(sourcePeerId.toInt64())
        var accepted = false
        let saved = self.updateValues(recordOperations: false) { values in
            var account = values[accountKey] ?? VisualGramAppearance()
            var channels = account.visualChannels ?? [:]
            var record = channels[channelKey]
            guard change(&record) else { return }
            accepted = true
            guard channels[channelKey] != record else { return }
            channels[channelKey] = record
            account.visualChannels = channels.isEmpty ? nil : channels
            values[accountKey] = account
        }
        return saved && accepted
    }
}
