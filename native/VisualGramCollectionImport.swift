import Foundation
import Postbox
import SwiftSignalKit
internal import TelegramApi

/// Read-only public collection loading. No ownership or gift-transfer RPCs are used.
public enum VisualGramCollectionImport {
    public enum ImportError: Error { case network, unavailable, invalidPagination, tooLarge }

    public struct Item {
        public let gift: StarGift.UniqueGift
        public let date: Int32
        public init(gift: StarGift.UniqueGift, date: Int32) { self.gift = gift; self.date = date }
    }

    public static func username(from input: String) -> String? {
        var name = input.trimmingCharacters(in: .whitespacesAndNewlines)
        if name.hasPrefix("@") { name.removeFirst() }
        guard name.range(of: "^[A-Za-z][A-Za-z0-9_]{3,31}$", options: .regularExpression) != nil else { return nil }
        return name
    }

    struct Pages {
        private(set) var items: [Item] = []
        private var slugs = Set<String>()
        private var offsets: Set<String> = [""]
        private var pageCount = 0
        let maxItems: Int
        init(maxItems: Int = 5000) { self.maxItems = maxItems }

        mutating func append(_ page: [Item], nextOffset: String?) throws -> String? {
            self.pageCount += 1
            guard self.pageCount <= 200 else { throw ImportError.tooLarge }
            for item in page where self.slugs.insert(item.gift.slug.lowercased()).inserted {
                guard self.items.count < self.maxItems else { throw ImportError.tooLarge }
                self.items.append(item)
            }
            guard let nextOffset, !nextOffset.isEmpty else { return nil }
            guard self.offsets.insert(nextOffset).inserted else { throw ImportError.invalidPagination }
            return nextOffset
        }
    }

    // NETWORK: keep collection reads separate from the local appearance overlay and its cache.
    public static func load(account: Account, peerId: EnginePeer.Id) -> Signal<[Item], ImportError> {
        return account.postbox.transaction { transaction -> Api.InputPeer? in
            transaction.getPeer(peerId).flatMap(apiInputPeer)
        }
        |> castError(ImportError.self)
        |> mapToSignal { inputPeer -> Signal<[Item], ImportError> in
            guard let inputPeer else { return .fail(.unavailable) }
            func page(offset: String, accumulated: Pages) -> Signal<[Item], ImportError> {
                // Exclude hidden and non-unique gifts; only visible collectible gifts are requested.
                let flags: Int32 = (1 << 0) | (1 << 2) | (1 << 7) | (1 << 8)
                return account.network.request(Api.functions.payments.getSavedStarGifts(flags: flags, peer: inputPeer, collectionId: nil, offset: offset, limit: 100))
                |> mapError { _ -> ImportError in .network }
                |> mapToSignal { result -> Signal<[Item], ImportError> in
                    return account.postbox.transaction { transaction -> ([Item], String?, Int) in
                        switch result {
                        case let .savedStarGifts(data):
                            updatePeers(transaction: transaction, accountPeerId: account.peerId, peers: AccumulatedPeers(transaction: transaction, chats: data.chats, users: data.users))
                            let items = data.gifts.compactMap { saved -> Item? in
                                guard let parsed = ProfileGiftsContext.State.StarGift(apiSavedStarGift: saved, peerId: peerId, transaction: transaction), parsed.savedToProfile, case let .unique(gift) = parsed.gift else { return nil }
                                return Item(gift: gift, date: parsed.date)
                            }
                            return (items, data.nextOffset, data.gifts.count)
                        }
                    }
                    |> castError(ImportError.self)
                    |> mapToSignal { items, nextOffset, rawCount -> Signal<[Item], ImportError> in
                        var accumulated = accumulated
                        // A server page may contain no usable unique items, but still advance.
                        if rawCount == 0, let nextOffset, !nextOffset.isEmpty { return .fail(.invalidPagination) }
                        do {
                            let next = try accumulated.append(items, nextOffset: nextOffset)
                            if let next { return page(offset: next, accumulated: accumulated) }
                            return .single(accumulated.items)
                        } catch let error as ImportError { return .fail(error) }
                        catch { return .fail(.invalidPagination) }
                    }
                }
            }
            return page(offset: "", accumulated: Pages())
        }
    }
}

public extension VisualGramLocalAppearance {
    /// Only add new collection objects. Do not fabricate chats, receipts, senders or payments.
    @discardableResult
    static func appendPublicCollection(_ items: [VisualGramCollectionImport.Item], into value: inout VisualGramAppearance) -> Int {
        var slugs = Set(value.gifts.compactMap { local -> String? in
            guard local.direction == .received, local.isHistoryOnly != true, case let .unique(gift) = local.gift else { return nil }
            return gift.slug.lowercased()
        })
        let previousOrder = Self.orderedOwnedGifts(in: value).map { $0.identifier }
        var added: [VisualGramGift] = []
        for item in items where slugs.insert(item.gift.slug.lowercased()).inserted {
            var local = VisualGramGift(gift: .unique(item.gift), counterpartyId: nil, date: item.date, text: "")
            local.savedToProfile = true
            local.pinnedToTop = false
            added.append(local)
        }
        guard !added.isEmpty else { return 0 }
        if value.giftOperationHistory == nil { value.giftOperationHistory = Self.giftOperations(in: value) }
        value.gifts.append(contentsOf: added)
        value.giftOrder = previousOrder + added.map { $0.identifier }
        value.enabled = true
        return added.count
    }

    func importPublicCollection(accountId: EnginePeer.Id, targetPeerId: EnginePeer.Id, items: [VisualGramCollectionImport.Item]) -> Int? {
        guard VisualGramActivation.shared.hasAccess else { return nil }
        var addedIds: [String] = []
        self.updateValues(recordOperations: false) { values in
            let key = String(targetPeerId.toInt64())
            var value = values[key] ?? VisualGramAppearance()
            let previousIds = Set(value.gifts.map { $0.identifier })
            Self.appendPublicCollection(items, into: &value)
            addedIds = value.gifts.filter { !previousIds.contains($0.identifier) }.map { $0.identifier }
            values[key] = value
        }
        guard VisualGramActivation.shared.hasAccess else { return nil }
        let savedIds = Set(self.appearance(accountId: accountId, targetPeerId: targetPeerId).gifts.map { $0.identifier })
        return addedIds.allSatisfy { savedIds.contains($0) } ? addedIds.count : nil
    }
}
