import Foundation
import Postbox
import TelegramCore
import AccountContext
import TelegramPresentationData
import ChatHistoryEntry

// These entries exist only in the rendered list. No history or outbox is written.
func visualGramChatGiftEntries(context: AccountContext, peerId: PeerId, peer: Peer?, accountPeer: EnginePeer?, view: MessageHistoryView, presentationData: ChatPresentationData) -> [ChatHistoryEntry] {
    guard let peer, peerId.namespace == Namespaces.Peer.CloudUser else { return [] }
    let localGifts = VisualGramLocalAppearance.shared.chatGifts(accountId: context.account.peerId, peerId: peerId)
    var result: [ChatHistoryEntry] = []
    var peers = SimpleDictionary<PeerId, Peer>()
    peers[peerId] = peer
    let ownId = context.account.peerId
    let ownPeer = accountPeer?._asPeer() ?? view.entries.lazy.compactMap { $0.message.peers[ownId] }.first
    if let ownPeer { peers[ownId] = ownPeer }

    func appendGift(identifier: String, date: Int32, version: UInt32, incoming: Bool, author: Peer?, action: TelegramMediaActionType, attributes: [MessageAttribute] = []) {
        if view.earlierId != nil, let first = view.entries.first, date < first.message.timestamp { return }
        if view.laterId != nil, let last = view.entries.last, date > last.message.timestamp { return }
        var hash: UInt32 = 2166136261
        for byte in identifier.utf8 { hash = (hash ^ UInt32(byte)) &* 16777619 }
        let message = Message(stableId: UInt32.max - 10000 - (hash % 100_000_000), stableVersion: version, id: MessageId(peerId: peerId, namespace: Int32.max - 42, id: -Int32(hash & 0x3fffffff) - 1), globallyUniqueId: nil, groupingKey: nil, groupInfo: nil, threadId: nil, timestamp: date, flags: incoming ? [.Incoming] : [], tags: [], globalTags: [], localTags: [], customTags: [], forwardInfo: nil, author: author, text: "", attributes: attributes, media: [TelegramMediaAction(action: action)], peers: peers, associatedMessages: SimpleDictionary<MessageId, Message>(), associatedMessageIds: [], associatedMedia: [:], associatedThreadInfo: nil, associatedStories: [:])
        result.append(.MessageEntry(message, presentationData, true, nil, .none, ChatMessageEntryAttributes()))
    }

    for local in localGifts {
        var version = UInt32(bitPattern: local.date)
        for byte in local.text.utf8 { version = (version ^ UInt32(byte)) &* 16777619 }
        for byte in "\(local.assetIdentifier):\(local.purchaseStars ?? local.purchaseGrams ?? 0):\(local.savedToProfile ?? true):\(local.nameHidden ?? false):\(local.counterpartyId ?? 0):\(local.direction.rawValue)".utf8 { version = (version ^ UInt32(byte)) &* 16777619 }
        if let entities = local.textEntities {
            let encoder = JSONEncoder(); encoder.outputFormatting = .sortedKeys
            if let data = try? encoder.encode(entities) { for byte in data { version = (version ^ UInt32(byte)) &* 16777619 } }
        }
        let gift = local.displayGift(accountId: context.account.peerId)
        let incoming = local.direction == .received
        let senderId = incoming ? peerId : context.account.peerId
        let recipientId = incoming ? context.account.peerId : peerId
        let action: TelegramMediaActionType
        switch gift {
        case .generic:
            action = .starGift(gift: gift, convertStars: nil, text: local.text.isEmpty ? nil : local.text, entities: local.textEntities, nameHidden: local.nameHidden ?? false, savedToProfile: incoming, converted: false, upgraded: false, canUpgrade: false, upgradeStars: nil, isRefunded: false, isPrepaidUpgrade: false, upgradeMessageId: nil, peerId: nil, senderId: senderId, savedId: nil, prepaidUpgradeHash: nil, giftMessageId: nil, upgradeSeparate: false, isAuctionAcquired: false, toPeerId: recipientId, number: nil)
        case .unique:
            action = .starGiftUnique(gift: gift, isUpgrade: false, isTransferred: local.isTransferred ?? false, savedToProfile: incoming, canExportDate: nil, transferStars: nil, isRefunded: false, isPrepaidUpgrade: false, peerId: nil, senderId: (local.purchaseStars == nil && local.purchaseGrams == nil) ? senderId : nil, savedId: nil, resaleAmount: local.purchaseGrams.map { CurrencyAmount(amount: StarsAmount(value: $0, nanos: 0), currency: .ton) } ?? local.purchaseStars.map { CurrencyAmount(amount: StarsAmount(value: $0, nanos: 0), currency: .stars) }, canTransferDate: nil, canResaleDate: nil, dropOriginalDetailsStars: nil, assigned: false, fromOffer: false, canCraftAt: incoming && local.isCrafted != true && !local.isBurnedCollectible && (local.craftChance ?? 0) > 0 ? (local.canCraftAt ?? 0) : nil, isCrafted: local.isCrafted ?? false, text: local.text.isEmpty ? nil : local.text, entities: local.textEntities, nameHidden: local.nameHidden ?? false)
        }
        let purchaseAuthor = local.purchaseBuyerId.flatMap { peers[EnginePeer.Id($0)] }
        let attributes: [MessageAttribute] = (local.purchaseStars ?? local.purchaseGrams).map { _ in [VisualGramGiftPurchaseAttribute(stars: local.purchaseStars ?? 0, grams: local.purchaseGrams)] } ?? []
        appendGift(identifier: local.identifier, date: local.date, version: version, incoming: incoming, author: purchaseAuthor ?? (incoming ? peer : ownPeer), action: action, attributes: attributes)
    }
    if peerId != ownId {
        for (sender, recipient, incoming) in [(ownId, peerId, false), (peerId, ownId, true)] {
            let appearance = VisualGramLocalAppearance.shared.appearance(accountId: ownId, targetPeerId: sender)
            guard appearance.enabled else { continue }
            for gift in appearance.premiumGifts ?? [] where gift.recipientId == recipient.toInt64() {
                guard gift.months > 0, gift.months <= Int32.max / 30 else { continue }
                let action = TelegramMediaActionType.giftPremium(currency: "XTR", amount: gift.stars, days: gift.months * 30, cryptoCurrency: nil, cryptoAmount: nil, text: gift.text.isEmpty ? nil : gift.text, entities: gift.entities)
                appendGift(identifier: gift.id, date: gift.date, version: 0, incoming: incoming, author: incoming ? peer : ownPeer, action: action)
            }
        }
    }
    return result
}
