import Foundation
import Postbox

// These messages are rendered from the local gift store in both chat surfaces.
public func visualGramChatGiftMessages(accountPeerId ownId: EnginePeer.Id, peer: EnginePeer, accountPeer: EnginePeer?, fromTimestamp: Int32?, throughTimestamp: Int32?, includePremium: Bool = true) -> [EngineMessage] {
    let peerId = peer.id
    guard peerId.namespace == Namespaces.Peer.CloudUser else { return [] }
    let localGifts = VisualGramLocalAppearance.shared.chatGifts(accountId: ownId, peerId: peerId)
    var result: [EngineMessage] = []
    var peers = SimpleDictionary<PeerId, Peer>()
    let chatPeer = peer._asPeer()
    peers[peerId] = chatPeer
    let hidden = VisualGramLocalAppearance.shared.hiddenChatGiftKeys(accountId: ownId, peerId: peerId)
    let ownPeer = accountPeer?._asPeer()
    if let ownPeer { peers[ownId] = ownPeer }

    func includesDate(_ date: Int32) -> Bool {
        return (fromTimestamp.map { date >= $0 } ?? true) && (throughTimestamp.map { date <= $0 } ?? true)
    }

    func appendGift(identifier: String, date: Int32, version: UInt32, incoming: Bool, author: Peer?, action: TelegramMediaActionType, attributes: [MessageAttribute] = []) {
        let hash = VisualGramLocalAppearance.chatGiftHash(identifier)
        let message = Message(stableId: UInt32.max - 10000 - (hash % 100_000_000), stableVersion: version, id: MessageId(peerId: peerId, namespace: Int32.max - 42, id: -Int32(hash & 0x3fffffff) - 1), globallyUniqueId: nil, groupingKey: nil, groupInfo: nil, threadId: nil, timestamp: date, flags: incoming ? [.Incoming] : [], tags: [], globalTags: [], localTags: [], customTags: [], forwardInfo: nil, author: author, text: "", attributes: attributes, media: [TelegramMediaAction(action: action)], peers: peers, associatedMessages: SimpleDictionary<MessageId, Message>(), associatedMessageIds: [], associatedMedia: [:], associatedThreadInfo: nil, associatedStories: [:])
        result.append(EngineMessage(message))
    }

    for local in localGifts where includesDate(local.date) {
        let sender = local.direction == .received ? peerId : ownId
        guard !hidden.contains(VisualGramLocalAppearance.chatGiftVisibilityKey(local, sender: sender.toInt64())) else { continue }
        var version = UInt32(bitPattern: local.date)
        for byte in local.text.utf8 { version = (version ^ UInt32(byte)) &* 16777619 }
        for byte in "\(local.assetIdentifier):\(local.purchaseStars ?? local.purchaseGrams ?? 0):\(local.savedToProfile ?? true):\(local.nameHidden ?? false):\(local.counterpartyId ?? 0):\(local.direction.rawValue)".utf8 { version = (version ^ UInt32(byte)) &* 16777619 }
        if let entities = local.textEntities {
            let encoder = JSONEncoder(); encoder.outputFormatting = .sortedKeys
            if let data = try? encoder.encode(entities) { for byte in data { version = (version ^ UInt32(byte)) &* 16777619 } }
        }
        let gift = local.displayGift(accountId: ownId)
        let incoming = local.direction == .received
        let senderId = incoming ? peerId : ownId
        let recipientId = incoming ? ownId : peerId
        let action: TelegramMediaActionType
        switch gift {
        case .generic:
            action = .starGift(gift: gift, convertStars: nil, text: local.text.isEmpty ? nil : local.text, entities: local.textEntities, nameHidden: local.nameHidden ?? false, savedToProfile: incoming, converted: false, upgraded: false, canUpgrade: false, upgradeStars: nil, isRefunded: false, isPrepaidUpgrade: false, upgradeMessageId: nil, peerId: nil, senderId: senderId, savedId: nil, prepaidUpgradeHash: nil, giftMessageId: nil, upgradeSeparate: false, isAuctionAcquired: false, toPeerId: recipientId, number: nil)
        case .unique:
            action = .starGiftUnique(gift: gift, isUpgrade: false, isTransferred: local.isTransferred ?? false, savedToProfile: incoming, canExportDate: nil, transferStars: nil, isRefunded: false, isPrepaidUpgrade: false, peerId: nil, senderId: (local.purchaseStars == nil && local.purchaseGrams == nil) ? senderId : nil, savedId: nil, resaleAmount: local.purchaseGrams.map { CurrencyAmount(amount: StarsAmount(value: $0, nanos: 0), currency: .ton) } ?? local.purchaseStars.map { CurrencyAmount(amount: StarsAmount(value: $0, nanos: 0), currency: .stars) }, canTransferDate: nil, canResaleDate: nil, dropOriginalDetailsStars: nil, assigned: false, fromOffer: false, canCraftAt: incoming && local.isCrafted != true && !local.isBurnedCollectible && (local.craftChance ?? 0) > 0 ? (local.canCraftAt ?? 0) : nil, isCrafted: local.isCrafted ?? false, text: local.text.isEmpty ? nil : local.text, entities: local.textEntities, nameHidden: local.nameHidden ?? false)
        }
        let purchaseAuthor = local.purchaseBuyerId.flatMap { peers[EnginePeer.Id($0)] }
        let attributes: [MessageAttribute] = (local.purchaseStars ?? local.purchaseGrams).map { _ in [VisualGramGiftPurchaseAttribute(stars: local.purchaseStars ?? 0, grams: local.purchaseGrams)] } ?? []
        appendGift(identifier: local.identifier, date: local.date, version: version, incoming: incoming, author: purchaseAuthor ?? (incoming ? chatPeer : ownPeer), action: action, attributes: attributes)
    }
    let appearance = VisualGramLocalAppearance.shared.appearance(accountId: ownId)
    if appearance.enabled {
        for transfer in appearance.gramHistory ?? [] where transfer.kind == .transfer && transfer.peerId == peerId.toInt64() && includesDate(transfer.date) {
            guard transfer.amount != 0, transfer.amount != Int64.min, !hidden.contains(transfer.id) else { continue }
            let incoming = transfer.amount > 0
            appendGift(identifier: transfer.id, date: transfer.date, version: 0, incoming: incoming, author: incoming ? chatPeer : ownPeer, action: .gramTransfer(amount: abs(transfer.amount), peerAddress: "", transactionId: transfer.id, comment: transfer.comment, commentEncrypted: false))
        }
    }
    if includePremium && peerId != ownId {
        for (sender, recipient, incoming) in [(ownId, peerId, false), (peerId, ownId, true)] {
            let appearance = VisualGramLocalAppearance.shared.appearance(accountId: ownId, targetPeerId: sender)
            guard appearance.enabled else { continue }
            for gift in appearance.premiumGifts ?? [] where gift.recipientId == recipient.toInt64() && includesDate(gift.date) {
                guard !hidden.contains(gift.id) else { continue }
                guard gift.months > 0, gift.months <= Int32.max / 30 else { continue }
                let action = TelegramMediaActionType.giftPremium(currency: "XTR", amount: gift.stars, days: gift.months * 30, cryptoCurrency: nil, cryptoAmount: nil, text: gift.text.isEmpty ? nil : gift.text, entities: gift.entities)
                appendGift(identifier: gift.id, date: gift.date, version: 0, incoming: incoming, author: incoming ? chatPeer : ownPeer, action: action)
            }
        }
    }
    return result
}
