"""Run the actual scheduling/migration Swift code with isolated engine dependencies."""
from pathlib import Path
import subprocess
import tempfile
from test_native_upgrade import STUBS as ENGINE_STUBS


def source():
    root = Path(__file__).resolve().parent.parent
    management = (root / "native/VisualGramGiftManagement.swift").read_text(encoding="utf-8")
    appearance = (root / "native/VisualGramLocalAppearance.swift").read_text(encoding="utf-8")
    model = management[management.index("public struct VisualGramScheduledGift:"):management.index("public extension VisualGramLocalAppearance")]
    methods = management[management.index("    func chatGifts("):management.index("    static func isLocalReference(")]
    appearance_model = appearance[appearance.index("public struct VisualGramPremiumGift:"):appearance.index("/// Local presentation data.")]
    reset = appearance[appearance.index("    public func reset("):appearance.index("    public func displayPeer(")]
    migration = appearance[appearance.index("    static func migrateLegacyAppearances("):appearance.index("    public var changes:")]
    access = appearance[appearance.index("    public func appearance("):appearance.index("    func updateValues(")]
    dispatch = appearance[appearance.index("    public var pendingScheduledGifts:"):appearance.index("    public func appearance(")]
    gift_model = appearance[appearance.index("public struct VisualGramGift:"):appearance.index("    public func displayGift(")] + "}\n"
    collection = (root / "native/VisualGramCollectionImport.swift").read_text(encoding="utf-8")
    collection_model = collection[collection.index("public enum VisualGramCollectionImport"):collection.index("    // NETWORK:")] + "}\n"
    collection_methods = collection[collection.index("    @discardableResult\n    static func appendPublicCollection"):]
    collection_support = management[management.index("    static func orderedOwnedGifts("):management.index("    static func recordGiftOperations(")]
    return ENGINE_STUBS + STUBS + gift_model + model + appearance_model + collection_model + STORE + migration + dispatch + access + reset + "}\npublic extension VisualGramLocalAppearance {\n" + collection_support + methods + collection_methods + CHECKS + COLLECTION_CHECKS


STUBS = r'''
import Foundation
public typealias VisualGramUsername = Int
public struct PeerVerification: Codable, Equatable {
    public let botId: Int64
    public let iconFileId: Int64
    public let description: String
    public let descriptionEntities: [Int]
}
public typealias PeerEmojiStatus = Int
public typealias TelegramStarRating = Int
public typealias TelegramStarPendingRating = Int
enum Namespaces { enum Peer { static let CloudUser: Int32 = 0 } }
extension EnginePeer.Id { var namespace: Int32 { 0 } }
public typealias VisualGramNameColor = Int
public typealias TelegramBusinessHours = Int
public typealias TelegramBusinessLocation = Int
public typealias VisualGramGiftCollection = Int
'''

STORE = r'''
public final class VisualGramLocalAppearance {
    private let lock = NSLock()
    private let defaults = UserDefaults(suiteName: UUID().uuidString)!
    private var vaultKey: Data? = Data(repeating: 7, count: 32)
    var values: [String: VisualGramAppearance] = [:]
    func updateValues(recordOperations: Bool = true, allowWhileLocked: Bool = false, _ change: (inout [String: VisualGramAppearance]) -> Void) { change(&values) }
'''

CHECKS = r'''
let store = VisualGramLocalAppearance()
let own = EnginePeer.Id(10), other = EnginePeer.Id(20), secondAccount = EnginePeer.Id(30)
let ordinary = StarGift.generic(.init(id: 42, title: "Bear", availability: nil, releasedBy: nil))
let gift = VisualGramGift(gift: ordinary, counterpartyId: 20, direction: .sent, date: 5, text: "")
store.scheduleGift(accountId: own, targetPeerId: own, gift: gift, deliveryDate: 100)
assert(store.appearance(accountId: own).gifts.isEmpty, "scheduled card leaked before delivery")
assert(store.deliverScheduledGifts(accountId: own, now: 99).isEmpty, "delivered too early")
let due = store.deliverScheduledGifts(accountId: own, now: 100)
assert(due.count == 1 && store.appearance(accountId: own).gifts.first?.date == 100)
assert(store.deliverScheduledGifts(accountId: own, now: 101).isEmpty, "delivered twice")
assert(store.appearance(accountId: secondAccount).gifts.isEmpty, "cross-account delivery")
store.scheduleGift(accountId: own, targetPeerId: own, gift: gift, deliveryDate: 200)
store.scheduleGift(accountId: own, targetPeerId: own, gift: gift, deliveryDate: 300)
assert(store.appearance(accountId: own).scheduledGifts?.count == 1, "reschedule duplicated pending gift")
assert(store.deliverScheduledGifts(accountId: own, now: 200).isEmpty, "ignored reschedule")
store.scheduleGift(accountId: own, targetPeerId: other, gift: gift, deliveryDate: 400)
store.scheduleGift(accountId: secondAccount, targetPeerId: own, gift: gift, deliveryDate: 350)
store.update(accountId: own) {
    $0.premium = true
    $0.stars = 123
    $0.grams = 456
    $0.usernames = [1]
    $0.giftOperationHistory = [gift]
    $0.gramCardPlacements = [:]
}
let otherBeforeReset = store.appearance(accountId: other)
let otherSchedule = store.appearance(accountId: own).scheduledGifts?.filter { $0.targetPeerId == other.toInt64() }
store.reset(accountId: own)
var cleared = VisualGramAppearance()
cleared.scheduledGifts = otherSchedule
assert(store.appearance(accountId: own) == cleared, "reset left profile data or removed another profile's queue")
assert(store.appearance(accountId: other) == otherBeforeReset, "reset changed another profile")
assert(store.deliverScheduledGifts(accountId: secondAccount, now: 350).isEmpty, "reset left a gift queued from another account")
let encoded = try JSONEncoder().encode(store.values)
let restored = try JSONDecoder().decode([String: VisualGramAppearance].self, from: encoded)
let reopened = VisualGramLocalAppearance()
reopened.values = restored
assert(reopened.deliverScheduledGifts(accountId: own, now: 500).count == 1, "pending queue lost on restart")
assert(reopened.appearance(accountId: own, targetPeerId: other).gifts.first?.date == 400)
assert(reopened.appearance(accountId: own).gifts.isEmpty, "wrong profile")
let deletion = VisualGramLocalAppearance()
let messageId = -Int32(VisualGramLocalAppearance.chatGiftHash(gift.identifier) & 0x3fffffff) - 1
let giftKey = VisualGramLocalAppearance.chatGiftVisibilityKey(gift, sender: own.toInt64())
deletion.addGift(accountId: own, targetPeerId: own, gift: gift)
deletion.hideChatGifts(accountId: own, peerId: other, messageId: messageId, forEveryone: false)
assert(deletion.hiddenChatGiftKeys(accountId: own, peerId: other) == [giftKey])
assert(deletion.hiddenChatGiftKeys(accountId: other, peerId: own).isEmpty)
assert(deletion.appearance(accountId: other).gifts.count == 1, "chat deletion removed the owned gift")
let premium = VisualGramPremiumGift(id: "premium", recipientId: other.toInt64(), date: 500, months: 1, stars: 100, text: "", entities: [])
deletion.update(accountId: own) { $0.premiumGifts = [premium] }
deletion.hideChatGifts(accountId: own, peerId: other, forEveryone: true)
assert(deletion.hiddenChatGiftKeys(accountId: other, peerId: own) == [giftKey, premium.id])
assert(deletion.hiddenChatGiftKeys(accountId: secondAccount, peerId: own).isEmpty)
deletion.addGift(accountId: own, targetPeerId: own, gift: VisualGramGift(gift: ordinary, counterpartyId: other.toInt64(), direction: .sent, date: 600, text: ""))
assert(deletion.hiddenChatGiftKeys(accountId: own, peerId: other).count == 2, "chat deletion affected future gifts")
let deletedReload = try JSONDecoder().decode([String: VisualGramAppearance].self, from: JSONEncoder().encode(deletion.values))
assert(deletedReload["20"]?.hiddenChatGifts?["10"] == [giftKey, premium.id])
reopened.scheduleGift(accountId: own, targetPeerId: own, gift: gift, deliveryDate: 600)
reopened.update(accountId: own) { $0.scheduledGifts = [] }
assert(reopened.deliverScheduledGifts(accountId: own, now: 600).isEmpty, "cancelled gift delivered")
reopened.scheduleGift(accountId: own, targetPeerId: other, gift: gift, deliveryDate: 700)
reopened.reset(accountId: own, targetPeerId: other)
assert(reopened.deliverScheduledGifts(accountId: own, now: 700).isEmpty, "profile reset kept its queue")
let oldData = #"{"enabled":true,"premium":false,"verified":false,"usernames":[],"overridesEmojiStatus":false,"gifts":[],"controlBot":{"peerId":999,"username":"old-bot","pairedAt":100,"lastMessageId":2}}"#.data(using: .utf8)!
let migrated = try JSONDecoder().decode(VisualGramAppearance.self, from: oldData)
assert(migrated.enabled && migrated.scheduledGifts == nil)
let migratedJson = String(data: try JSONEncoder().encode(migrated), encoding: .utf8)!
assert(!migratedJson.contains("controlBot"), "obsolete bot connection persisted")
var legacyProfile = try JSONSerialization.jsonObject(with: oldData) as! [String: Any]
legacyProfile["stars"] = 123456
legacyProfile["verification"] = ["botId": Int64(42), "iconFileId": Int64(999), "description": "Major"]
legacyProfile["majorTemplate"] = legacyProfile["verification"]
var legacyNested = legacyProfile
legacyNested["stars"] = 789
legacyProfile["peerOverrides"] = ["20": legacyNested]
let legacyVerificationData = try JSONSerialization.data(withJSONObject: ["10": legacyProfile])
assert((try? JSONDecoder().decode([String: VisualGramAppearance].self, from: legacyVerificationData)) == nil, "fixture must require compatibility migration")
let compatibleProfiles = VisualGramLocalAppearance.decodeStoredAppearances(legacyVerificationData)!
assert(compatibleProfiles["10"]?.stars == 123456 && compatibleProfiles["10"]?.verification?.description == "Major", "older verification discarded the profile")
assert(compatibleProfiles["10"]?.majorTemplate?.descriptionEntities == [], "older Major template not migrated")
assert(compatibleProfiles["10"]?.peerOverrides?["20"]?.stars == 789 && compatibleProfiles["10"]?.peerOverrides?["20"]?.verification?.descriptionEntities == [], "nested v2 verification lost")
let compatibleData = try JSONEncoder().encode(compatibleProfiles)
assert(VisualGramLocalAppearance.decodeStoredAppearances(compatibleData) == compatibleProfiles, "current profiles changed on reload")
assert(VisualGramLocalAppearance.decodeStoredAppearances(Data("invalid".utf8)) == nil, "malformed data accepted")
reopened.update(accountId: own) { $0.enabled = true; $0.verified = true; $0.premium = true; $0.stars = 999 }
assert(reopened.appearance(accountId: secondAccount, targetPeerId: own) == reopened.appearance(accountId: own), "profile differs between accounts")
assert(!reopened.appearance(accountId: secondAccount).verified, "another identity inherited own badge")
reopened.update(accountId: secondAccount, targetPeerId: own) { $0.verified = false }
assert(!reopened.appearance(accountId: own).verified, "edit from second account not shared")
var legacyOwn = VisualGramAppearance(); legacyOwn.enabled = true; legacyOwn.verified = true
var foreign = VisualGramAppearance(); foreign.enabled = true; foreign.premium = true
legacyOwn.peerOverrides = ["20": foreign]
let flattened = VisualGramLocalAppearance.migrateLegacyAppearances(["10": legacyOwn, "20": VisualGramAppearance()])
assert(flattened["10"]?.verified == true && flattened["20"]?.premium == true, "v2 profile lost during shared migration")
assert(flattened.values.allSatisfy { $0.peerOverrides == nil }, "legacy overrides not flattened")
reopened.reset(accountId: secondAccount, targetPeerId: own)
assert(!reopened.appearance(accountId: own).enabled, "reset not shared")
var incoming = gift; incoming.direction = .received; incoming.counterpartyId = secondAccount.toInt64()
reopened.addGift(accountId: own, targetPeerId: own, gift: incoming)
let reverse = reopened.chatGifts(accountId: secondAccount, peerId: own)
assert(reverse.count == 1 && reverse[0].direction == .sent && reverse[0].counterpartyId == own.toInt64(), "reciprocal chat missing on another account")
reopened.scheduleGift(accountId: own, targetPeerId: own, gift: gift, deliveryDate: 800)
let pendingId = reopened.pendingScheduledGifts[0].id
reopened.rescheduleGift(id: pendingId, deliveryDate: 900)
assert(reopened.deliverAllScheduledGifts(now: 800).isEmpty, "shared reschedule ignored")
assert(reopened.deliverAllScheduledGifts(now: 900).count == 1, "shared foreground delivery lost")
reopened.scheduleGift(accountId: own, targetPeerId: own, gift: gift, deliveryDate: 1000)
reopened.cancelScheduledGift(id: reopened.pendingScheduledGifts[0].id)
assert(reopened.deliverAllScheduledGifts(now: 1000).isEmpty, "shared cancellation ignored")
var scheduledIncoming = gift
scheduledIncoming.direction = .received
scheduledIncoming.counterpartyId = secondAccount.toInt64()
scheduledIncoming.localIdentifier = "received:30:scheduled"
reopened.scheduleGift(accountId: secondAccount, targetPeerId: other, gift: scheduledIncoming, deliveryDate: 1200)
assert(!reopened.appearance(accountId: other).gifts.contains { $0.identifier == scheduledIncoming.identifier }, "incoming gift appeared before deadline")
assert(reopened.deliverAllScheduledGifts(now: 1199).isEmpty)
assert(reopened.deliverAllScheduledGifts(now: 1200).count == 1)
let received = reopened.appearance(accountId: other).gifts.first { $0.identifier == scheduledIncoming.identifier }!
assert(received.direction == .received && received.counterpartyId == secondAccount.toInt64() && received.date == 1200)
assert(reopened.deliverAllScheduledGifts(now: 1201).isEmpty, "incoming delivered twice")
let duplicates = VisualGramLocalAppearance()
let first = VisualGramGift(gift: ordinary, counterpartyId: 20, date: 1300, text: "same")
let second = VisualGramGift(gift: ordinary, counterpartyId: 20, date: 1300, text: "same")
assert(first.identifier != second.identifier && first.reference(accountId: own) != second.reference(accountId: own), "two ordinary instances share an identity")
duplicates.addGift(accountId: own, targetPeerId: own, gift: first)
duplicates.addGift(accountId: own, targetPeerId: own, gift: second)
duplicates.addGift(accountId: own, targetPeerId: own, gift: first)
assert(duplicates.appearance(accountId: own).gifts.count == 2, "same ordinary gifts replaced each other or retry duplicated an instance")
assert(duplicates.chatGifts(accountId: own, peerId: other).count == 2)
assert(duplicates.chatGifts(accountId: other, peerId: own).count == 2, "mirror lost identical gifts")
let third = VisualGramGift(gift: ordinary, counterpartyId: 20, direction: .sent, date: 5, text: "")
let fourth = VisualGramGift(gift: ordinary, counterpartyId: 20, direction: .sent, date: 5, text: "")
duplicates.scheduleGift(accountId: own, targetPeerId: own, gift: third, deliveryDate: 1400)
duplicates.scheduleGift(accountId: own, targetPeerId: own, gift: fourth, deliveryDate: 1400)
let restart = VisualGramLocalAppearance()
restart.values = try JSONDecoder().decode([String: VisualGramAppearance].self, from: JSONEncoder().encode(duplicates.values))
assert(restart.deliverAllScheduledGifts(now: 1399).isEmpty)
assert(restart.deliverAllScheduledGifts(now: 1400).count == 2, "one scheduled ordinary gift replaced the other")
assert(restart.deliverAllScheduledGifts(now: 1401).isEmpty)
assert(restart.appearance(accountId: own).gifts.count == 4)
print("PASS: distinct ordinary copies/references, reciprocal chats, simultaneous schedules/restart, exactly-once delivery, shared profiles and migration")
'''


COLLECTION_CHECKS = r'''
assert(VisualGramCollectionImport.username(from: " @Collectibles_1 \n") == "Collectibles_1")
for invalid in ["", "@", "@@user", "https://t.me/user", "a/b", "test?admin=1", "has space", "12345", String(repeating: "a", count: 33)] {
    assert(VisualGramCollectionImport.username(from: invalid) == nil, "invalid collection owner accepted")
}
func collectionItem(_ slug: String, date: Int32 = 10) -> VisualGramCollectionImport.Item {
    return .init(gift: StarGift.UniqueGift(id: 901, giftId: 9, title: "Collection", number: 1, slug: slug, owner: .peerId(other), attributes: [.model(91), .pattern(92), .backdrop(93)], availability: .init(issued: 1, total: 10), giftAddress: nil, resellAmounts: nil, resellForTonOnly: false, releasedBy: nil, valueAmount: nil, valueCurrency: nil, valueUsdAmount: nil, flags: [], themePeerId: nil, peerColor: nil, hostPeerId: nil, minOfferStars: nil, craftChancePermille: nil), date: date)
}
let publicA = collectionItem("Collectible-1"), publicB = collectionItem("Collectible-2", date: 20)
var pages = VisualGramCollectionImport.Pages()
let collectionOffset2 = try pages.append([publicA], nextOffset: "page2")
assert(collectionOffset2 == "page2")
let collectionOffset3 = try pages.append([], nextOffset: "page3")
assert(collectionOffset3 == "page3", "a filtered page prevented loading later gifts")
let collectionEnd = try pages.append([collectionItem("collectible-1"), publicB], nextOffset: "")
assert(collectionEnd == nil)
assert(pages.items.map { $0.gift.slug } == ["Collectible-1", "Collectible-2"], "pagination changed order or duplicated NFT")
do { _ = try pages.append([], nextOffset: "page2"); assertionFailure("repeated offset accepted") }
catch VisualGramCollectionImport.ImportError.invalidPagination {} catch { assertionFailure("unexpected page error") }
var limited = VisualGramCollectionImport.Pages(maxItems: 1)
do { _ = try limited.append([publicA, publicB], nextOffset: nil); assertionFailure("size limit ignored") }
catch VisualGramCollectionImport.ImportError.tooLarge {} catch { assertionFailure("unexpected limit error") }
let collectionStore = VisualGramLocalAppearance()
var retained = VisualGramGift(gift: ordinary, counterpartyId: nil, date: 5, text: "Keep me")
retained.pinnedToTop = true
collectionStore.addGift(accountId: own, targetPeerId: own, gift: retained)
collectionStore.update(accountId: own) { $0.stars = 345; $0.grams = 123456789; $0.premium = true }
let oldOperations = VisualGramLocalAppearance.giftOperations(in: collectionStore.appearance(accountId: own))
assert(collectionStore.importPublicCollection(accountId: own, targetPeerId: own, items: pages.items) == 2)
let imported = collectionStore.appearance(accountId: own)
assert(imported.gifts.count == 3 && imported.gifts[0] == retained, "collection import overwrote existing gift")
assert(imported.stars == 345 && imported.grams == 123456789 && imported.premium, "collection import changed profile or balances")
assert(VisualGramLocalAppearance.giftOperations(in: imported) == oldOperations, "collection import fabricated a receipt")
assert(collectionStore.chatGifts(accountId: own, peerId: other).isEmpty, "collection import fabricated a chat message")
assert(imported.gifts.dropFirst().allSatisfy { $0.counterpartyId == nil && $0.direction == .received && $0.savedToProfile == true })
assert(imported.giftOrder == imported.gifts.map { $0.identifier }, "source collection order not retained")
assert(collectionStore.appearance(accountId: other).gifts.isEmpty, "source profile changed")
assert(collectionStore.importPublicCollection(accountId: own, targetPeerId: own, items: [publicA, collectionItem("COLLECTIBLE-2")]) == 0)
let collectionReload = VisualGramLocalAppearance()
collectionReload.values = try JSONDecoder().decode([String: VisualGramAppearance].self, from: JSONEncoder().encode(collectionStore.values))
assert(collectionReload.appearance(accountId: own) == imported, "imported collection failed persistence round trip")
assert(collectionReload.importPublicCollection(accountId: own, targetPeerId: own, items: pages.items) == 0)
VisualGramActivation.shared.hasAccess = false
assert(collectionStore.importPublicCollection(accountId: own, targetPeerId: own, items: [collectionItem("Locked-1")]) == nil)
VisualGramActivation.shared.hasAccess = true
assert(collectionStore.appearance(accountId: own) == imported, "locked import changed saved data")
print("PASS: public NFT collection pagination, validation, stable order, duplicate suppression, atomic import, balance/chat/receipt isolation, restart and activation guard")
'''


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="visualgram-delivery-") as folder:
        swift = Path(folder) / "DeliveryTests.swift"
        executable = Path(folder) / "delivery-tests"
        swift.write_text(source(), encoding="utf-8")
        subprocess.run(["xcrun", "swiftc", str(swift), "-o", str(executable)], check=True)
        subprocess.run([str(executable)], check=True)
