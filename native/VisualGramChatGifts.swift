import Foundation
import Postbox
import TelegramCore
import AccountContext
import TelegramPresentationData
import ChatHistoryEntry

// These entries exist only in the rendered list. No history or outbox is written.
func visualGramChatGiftEntries(context: AccountContext, peerId: PeerId, peer: Peer?, view: MessageHistoryView, presentationData: ChatPresentationData) -> [ChatHistoryEntry] {
    guard let peer, peerId.namespace == Namespaces.Peer.CloudUser else { return [] }
    let localGifts = VisualGramLocalAppearance.shared.chatGifts(accountId: context.account.peerId, peerId: peerId)
    var result: [ChatHistoryEntry] = []
    for local in localGifts {
        if view.earlierId != nil, let first = view.entries.first, local.date < first.message.timestamp { continue }
        if view.laterId != nil, let last = view.entries.last, local.date > last.message.timestamp { continue }
        var hash: UInt32 = 2166136261
        for byte in local.identifier.utf8 { hash = (hash ^ UInt32(byte)) &* 16777619 }
        var version = UInt32(bitPattern: local.date)
        for byte in local.text.utf8 { version = (version ^ UInt32(byte)) &* 16777619 }
        let gift = local.displayGift(accountId: context.account.peerId)
        let incoming = local.direction == .received
        let senderId = incoming ? peerId : context.account.peerId
        let recipientId = incoming ? context.account.peerId : peerId
        let action: TelegramMediaActionType
        switch gift {
        case .generic:
            action = .starGift(gift: gift, convertStars: nil, text: local.text.isEmpty ? nil : local.text, entities: nil, nameHidden: false, savedToProfile: incoming, converted: false, upgraded: false, canUpgrade: false, upgradeStars: nil, isRefunded: false, isPrepaidUpgrade: false, upgradeMessageId: nil, peerId: nil, senderId: senderId, savedId: nil, prepaidUpgradeHash: nil, giftMessageId: nil, upgradeSeparate: false, isAuctionAcquired: false, toPeerId: recipientId, number: nil)
        case .unique:
            action = .starGiftUnique(gift: gift, isUpgrade: false, isTransferred: false, savedToProfile: incoming, canExportDate: nil, transferStars: nil, isRefunded: false, isPrepaidUpgrade: false, peerId: nil, senderId: senderId, savedId: nil, resaleAmount: nil, canTransferDate: nil, canResaleDate: nil, dropOriginalDetailsStars: nil, assigned: false, fromOffer: false, canCraftAt: nil, isCrafted: false)
        }
        var peers = SimpleDictionary<PeerId, Peer>()
        peers[peerId] = peer
        let ownPeer = view.entries.lazy.compactMap { $0.message.peers[context.account.peerId] }.first
        if let ownPeer { peers[context.account.peerId] = ownPeer }
        let message = Message(stableId: UInt32.max - 10000 - (hash % 100_000_000), stableVersion: version, id: MessageId(peerId: peerId, namespace: Int32.max - 42, id: -Int32(hash & 0x3fffffff) - 1), globallyUniqueId: nil, groupingKey: nil, groupInfo: nil, threadId: nil, timestamp: local.date, flags: incoming ? [.Incoming] : [], tags: [], globalTags: [], localTags: [], customTags: [], forwardInfo: nil, author: incoming ? peer : ownPeer, text: "", attributes: [], media: [TelegramMediaAction(action: action)], peers: peers, associatedMessages: SimpleDictionary<MessageId, Message>(), associatedMessageIds: [], associatedMedia: [:], associatedThreadInfo: nil, associatedStories: [:])
        result.append(.MessageEntry(message, presentationData, true, nil, .none, ChatMessageEntryAttributes()))
    }
    return result
}
