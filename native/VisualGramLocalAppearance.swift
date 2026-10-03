import Foundation
import SwiftSignalKit

public struct VisualGramUsername: Codable, Equatable {
    public var name: String
    public var purchaseDate: Int32
    public var tonAmount: Int64
    public var usdAmount: Int64

    public init(name: String, purchaseDate: Int32, tonAmount: Int64, usdAmount: Int64) {
        self.name = name
        self.purchaseDate = purchaseDate
        self.tonAmount = tonAmount
        self.usdAmount = usdAmount
    }

    public var collectibleInfo: TelegramCollectibleItemInfo {
        return TelegramCollectibleItemInfo(subject: .username(self.name), purchaseDate: self.purchaseDate, currency: "USD", currencyAmount: self.usdAmount, cryptoCurrency: "TON", cryptoCurrencyAmount: self.tonAmount, url: "https://fragment.com/username/\(self.name)")
    }
    public var collectiblePhoneInfo: TelegramCollectibleItemInfo {
        return TelegramCollectibleItemInfo(subject: .phoneNumber(self.name), purchaseDate: self.purchaseDate, currency: "USD", currencyAmount: self.usdAmount, cryptoCurrency: "TON", cryptoCurrencyAmount: self.tonAmount, url: "https://fragment.com/number/\(self.name)")
    }
}

public struct VisualGramGift: Codable, Equatable {
    public enum Direction: String, Codable { case received, sent }
    public var gift: StarGift
    public var counterpartyId: Int64?
    public var direction: Direction
    public var date: Int32
    public var text: String
    // Optional fields preserve saved v2 gifts from the first IPA.
    public var savedToProfile: Bool?
    public var pinnedToTop: Bool?
    public var collectionIds: [Int32]?
    public var localIdentifier: String?
    public var hidesOriginalInfo: Bool?
    public var isHistoryOnly: Bool?
    public var isTransferred: Bool?
    public var resaleStars: Int64?

    public init(gift: StarGift, counterpartyId: Int64?, direction: Direction = .received, date: Int32, text: String) {
        self.gift = gift
        self.counterpartyId = counterpartyId
        self.direction = direction
        self.date = date
        self.text = text
    }

    public var identifier: String {
        if let localIdentifier { return localIdentifier }
        return "\(self.direction.rawValue):\(self.counterpartyId ?? 0):\(self.assetIdentifier)"
    }

    public var assetIdentifier: String {
        switch self.gift {
        case let .generic(gift): return "generic:\(gift.id)"
        case let .unique(gift): return "unique:\(gift.slug)"
        }
    }

    public func reference(accountId: EnginePeer.Id) -> StarGiftReference {
        var hash: UInt32 = 2166136261
        for byte in self.identifier.utf8 { hash = (hash ^ UInt32(byte)) &* 16777619 }
        return .message(messageId: EngineMessage.Id(peerId: accountId, namespace: Int32.max - 42, id: -Int32(hash & 0x3fffffff) - 1))
    }

    public func displayGift(accountId: EnginePeer.Id) -> StarGift {
        guard case let .unique(gift) = self.gift else { return self.gift }
        let recipientId = self.direction == .sent ? (self.counterpartyId.map { EnginePeer.Id($0) } ?? accountId) : accountId
        let senderId = self.direction == .sent ? accountId : self.counterpartyId.map { EnginePeer.Id($0) }
        var attributes = gift.attributes.filter { $0.attributeType != .originalInfo }
        if self.hidesOriginalInfo != true { attributes.append(.originalInfo(senderPeerId: senderId, recipientPeerId: recipientId, date: self.date, text: self.text.isEmpty ? nil : self.text, entities: nil)) }
        let prices = self.resaleStars.map { [CurrencyAmount(currency: .stars, amount: StarsAmount(value: $0, nanos: 0))] }
        return .unique(StarGift.UniqueGift(id: gift.id, giftId: gift.giftId, title: gift.title, number: gift.number, slug: gift.slug, owner: .peerId(recipientId), attributes: attributes, availability: gift.availability, giftAddress: nil, resellAmounts: prices, resellForTonOnly: false, releasedBy: gift.releasedBy, valueAmount: gift.valueAmount, valueCurrency: gift.valueCurrency, valueUsdAmount: gift.valueUsdAmount, flags: gift.flags, themePeerId: gift.themePeerId, peerColor: gift.peerColor, hostPeerId: nil, minOfferStars: nil, craftChancePermille: nil))
    }

    public func profileGift(accountId: EnginePeer.Id, sender: EnginePeer?) -> ProfileGiftsContext.State.StarGift {
        let canUpgrade: Bool
        if case let .generic(gift) = self.gift { canUpgrade = gift.upgradeStars != nil && self.direction == .received && self.isHistoryOnly != true } else { canUpgrade = false }
        let transferStars: Int64?
        if case .unique = self.gift, self.direction == .received, self.isHistoryOnly != true { transferStars = 0 } else { transferStars = nil }
        return ProfileGiftsContext.State.StarGift(gift: self.displayGift(accountId: accountId), reference: self.reference(accountId: accountId), fromPeer: sender, date: self.date, text: self.text.isEmpty ? nil : self.text, entities: nil, nameHidden: false, savedToProfile: self.savedToProfile ?? true, pinnedToTop: self.pinnedToTop ?? false, convertStars: nil, canUpgrade: canUpgrade, canExportDate: nil, upgradeStars: nil, transferStars: transferStars, canTransferDate: nil, canResaleDate: nil, collectionIds: self.collectionIds, prepaidUpgradeHash: nil, upgradeSeparate: false, dropOriginalDetailsStars: nil, number: nil, isRefunded: false, canCraftAt: nil)
    }
}

public struct VisualGramAppearance: Codable, Equatable {
    public var enabled = false
    public var premium = false
    public var verified = false
    public var verification: PeerVerification?
    public var usernames: [VisualGramUsername] = []
    public var overridesEmojiStatus = false
    public var emojiStatus: PeerEmojiStatus?
    public var gifts: [VisualGramGift] = []
    public var stars: Int64?
    public var collections: [VisualGramGiftCollection]?
    public var scheduledGifts: [VisualGramScheduledGift]?
    public var peerOverrides: [String: VisualGramAppearance]?
    public var majorTemplate: PeerVerification?
    public var phoneNumber: VisualGramUsername?
    public var starRating: TelegramStarRating?

    public init() {
    }
}

/// Local presentation data. This store never writes peers to Postbox or sends RPCs.
public final class VisualGramLocalAppearance {
    public static let shared = VisualGramLocalAppearance()
    private let lock = NSLock()
    private let defaults: UserDefaults
    private let revision = ValuePromise<Int32>(0, ignoreRepeated: false)
    private var revisionValue: Int32 = 0
    private var values: [String: VisualGramAppearance]

    func snapshotValues() -> [String: VisualGramAppearance] {
        self.lock.lock()
        defer { self.lock.unlock() }
        return self.values
    }

    private init() {
        self.defaults = UserDefaults.standard
        if let data = self.defaults.data(forKey: "visualgram.appearance.v3"), let decoded = try? JSONDecoder().decode([String: VisualGramAppearance].self, from: data) {
            self.values = decoded
        } else if let data = self.defaults.data(forKey: "visualgram.appearance.v2"), let decoded = try? JSONDecoder().decode([String: VisualGramAppearance].self, from: data) {
            self.values = Self.migrateLegacyAppearances(decoded)
            if let migrated = try? JSONEncoder().encode(self.values) { self.defaults.set(migrated, forKey: "visualgram.appearance.v3") }
        } else {
            self.values = [:]
        }
    }

    static func migrateLegacyAppearances(_ legacy: [String: VisualGramAppearance]) -> [String: VisualGramAppearance] {
        var result: [String: VisualGramAppearance] = [:]
        for account in legacy.keys.sorted() {
            for (peer, value) in legacy[account]?.peerOverrides ?? [:] where result[peer] == nil {
                var profile = value
                profile.peerOverrides = nil
                profile.scheduledGifts = nil
                profile.majorTemplate = nil
                result[peer] = profile
            }
        }
        for account in legacy.keys.sorted() {
            var own = legacy[account]!
            own.peerOverrides = nil
            var profile = own
            profile.scheduledGifts = nil
            profile.majorTemplate = nil
            if profile != VisualGramAppearance() || result[account] == nil {
                result[account] = own
            } else {
                result[account]?.scheduledGifts = own.scheduledGifts
                result[account]?.majorTemplate = own.majorTemplate
            }
        }
        return result
    }

    public var changes: Signal<Int32, NoError> {
        return self.revision.get()
    }

    public var pendingScheduledGifts: [VisualGramScheduledGift] {
        self.lock.lock()
        defer { self.lock.unlock() }
        return self.values.values.flatMap { $0.scheduledGifts ?? [] }
    }

    public func deliverAllScheduledGifts(now: Int32) -> [VisualGramScheduledGift] {
        self.lock.lock()
        let accounts = self.values.compactMap { key, value -> EnginePeer.Id? in
            guard !(value.scheduledGifts ?? []).isEmpty, let id = Int64(key) else { return nil }
            return EnginePeer.Id(id)
        }
        self.lock.unlock()
        return accounts.flatMap { self.deliverScheduledGifts(accountId: $0, now: now) }
    }

    public func appearance(accountId: EnginePeer.Id, targetPeerId: EnginePeer.Id? = nil) -> VisualGramAppearance {
        self.lock.lock()
        defer { self.lock.unlock() }
        return self.values[String((targetPeerId ?? accountId).toInt64())] ?? VisualGramAppearance()
    }

    public func update(accountId: EnginePeer.Id, targetPeerId: EnginePeer.Id? = nil, _ transform: (inout VisualGramAppearance) -> Void) {
        self.updateValues { values in
            let key = String((targetPeerId ?? accountId).toInt64())
            var value = values[key] ?? VisualGramAppearance()
            transform(&value)
            value.peerOverrides = nil
            values[key] = value
        }
    }

    func updateValues(_ transform: (inout [String: VisualGramAppearance]) -> Void) {
        self.lock.lock()
        transform(&self.values)
        if let data = try? JSONEncoder().encode(self.values) {
            self.defaults.set(data, forKey: "visualgram.appearance.v3")
        }
        self.revisionValue &+= 1
        let revision = self.revisionValue
        self.lock.unlock()
        // Avoid rebuilding a visible native screen from inside its own action.
        Queue.mainQueue().async { self.revision.set(revision) }
    }

    public func reset(accountId: EnginePeer.Id, targetPeerId: EnginePeer.Id? = nil) {
        self.update(accountId: accountId, targetPeerId: targetPeerId) { value in
            let template = value.majorTemplate
            let scheduled = value.scheduledGifts
            value = VisualGramAppearance()
            value.majorTemplate = template
            value.scheduledGifts = scheduled
        }
        self.updateValues { values in
            for key in Array(values.keys) {
                values[key]?.scheduledGifts?.removeAll { $0.targetPeerId == (targetPeerId ?? accountId).toInt64() }
            }
        }
    }

    public func displayPeer(_ peer: EnginePeer?, accountId: EnginePeer.Id) -> EnginePeer? {
        guard case let .user(original) = peer else { return peer }
        let appearance = self.appearance(accountId: accountId, targetPeerId: original.id)
        guard appearance.enabled else { return peer }
        var flags = original.flags
        if appearance.premium { flags.insert(.isPremium) }
        if appearance.verified { flags.insert(.isVerified) }
        var user = original.withUpdatedFlags(flags)
        if let number = appearance.phoneNumber { user = user.withUpdatedPhone(number.name) }
        if appearance.overridesEmojiStatus {
            var status = appearance.emojiStatus
            if let expiration = status?.expirationDate, expiration <= Int32(Date().timeIntervalSince1970) { status = nil }
            user = user.withUpdatedEmojiStatus(status)
        }
        let existing = Set(user.usernames.map { $0.username.lowercased() })
        let added = appearance.usernames.filter { !existing.contains($0.name.lowercased()) }.map { TelegramPeerUsername(flags: [.isActive], username: $0.name) }
        user = user.withUpdatedUsernames(user.usernames + added)
        if user.addressName == nil, let first = added.first { user = user.withUpdatedUsername(first.username) }
        if let verification = appearance.verification {
            user = TelegramUser(id: user.id, accessHash: user.accessHash, firstName: user.firstName, lastName: user.lastName, username: user.username, phone: user.phone, photo: user.photo, botInfo: user.botInfo, restrictionInfo: user.restrictionInfo, flags: user.flags, emojiStatus: user.emojiStatus, usernames: user.usernames, storiesHidden: user.storiesHidden, nameColor: user.nameColor, backgroundEmojiId: user.backgroundEmojiId, profileColor: user.profileColor, profileBackgroundEmojiId: user.profileBackgroundEmojiId, subscriberCount: user.subscriberCount, verificationIconFileId: verification.iconFileId, linkedCommunityId: user.linkedCommunityId)
        }
        return .user(user)
    }

    public func localUsername(accountId: EnginePeer.Id, peerId: EnginePeer.Id, name: String) -> VisualGramUsername? {
        let appearance = self.appearance(accountId: accountId, targetPeerId: peerId)
        guard appearance.enabled else { return nil }
        return appearance.usernames.first { $0.name.lowercased() == name.lowercased() }
    }

    public func setLocalEmojiStatus(accountId: EnginePeer.Id, targetPeerId: EnginePeer.Id? = nil, status: PeerEmojiStatus?) -> Bool {
        guard self.appearance(accountId: accountId, targetPeerId: targetPeerId).enabled else { return false }
        self.update(accountId: accountId, targetPeerId: targetPeerId) { value in
            value.overridesEmojiStatus = true
            value.emojiStatus = status
        }
        return true
    }

    public func isLocalGift(accountId: EnginePeer.Id, gift: StarGift) -> Bool {
        let appearance = self.appearance(accountId: accountId)
        return appearance.gifts.contains { local in
            switch (local.gift, gift) {
            case let (.generic(lhs), .generic(rhs)): return lhs.id == rhs.id
            case let (.unique(lhs), .unique(rhs)): return lhs.slug == rhs.slug
            default: return false
            }
        }
    }

    public func setLocalGiftStatus(accountId: EnginePeer.Id, targetPeerId: EnginePeer.Id? = nil, gift: StarGift.UniqueGift, expirationDate: Int32?) -> Bool {
        var fileId: Int64?
        var patternId: Int64?
        var colors: (Int32, Int32, Int32, Int32)?
        for attribute in gift.attributes {
            switch attribute {
            case let .model(_, file, _, _): fileId = file.fileId.id
            case let .pattern(_, file, _): patternId = file.fileId.id
            case let .backdrop(_, _, inner, outer, pattern, text, _): colors = (inner, outer, pattern, text)
            default: break
            }
        }
        guard let fileId, let patternId, let colors else { return false }
        return self.setLocalEmojiStatus(accountId: accountId, targetPeerId: targetPeerId, status: PeerEmojiStatus(content: .starGift(id: gift.id, fileId: fileId, title: gift.title, slug: gift.slug, patternFileId: patternId, innerColor: colors.0, outerColor: colors.1, patternColor: colors.2, textColor: colors.3), expirationDate: expirationDate))
    }
}
