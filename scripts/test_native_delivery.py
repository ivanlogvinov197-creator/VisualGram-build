"""Run the actual scheduling/migration Swift code with isolated engine dependencies."""
from pathlib import Path
import subprocess
import tempfile


def source():
    root = Path(__file__).resolve().parent.parent
    management = (root / "native/VisualGramGiftManagement.swift").read_text(encoding="utf-8")
    appearance = (root / "native/VisualGramLocalAppearance.swift").read_text(encoding="utf-8")
    model = management[management.index("public struct VisualGramScheduledGift:"):management.index("public extension VisualGramLocalAppearance")]
    methods = management[management.index("    func chatGifts("):management.index("    static func isLocalReference(")]
    appearance_model = appearance[appearance.index("public struct VisualGramAppearance:"):appearance.index("/// Local presentation data.")]
    reset = appearance[appearance.index("    public func reset("):appearance.index("    public func displayPeer(")]
    migration = appearance[appearance.index("    static func migrateLegacyAppearances("):appearance.index("    public var changes:")]
    access = appearance[appearance.index("    public func appearance("):appearance.index("    func updateValues(")]
    dispatch = appearance[appearance.index("    public var pendingScheduledGifts:"):appearance.index("    public func appearance(")]
    return STUBS + model + appearance_model + STORE + migration + dispatch + access + reset + "}\npublic extension VisualGramLocalAppearance {\n" + methods + "}\n" + CHECKS


STUBS = r'''
import Foundation
public enum EnginePeer {
    public struct Id: Codable, Hashable {
        let value: Int64
        public init(_ value: Int64) { self.value = value }
        public func toInt64() -> Int64 { self.value }
    }
}
public typealias VisualGramUsername = Int
public typealias PeerVerification = Int
public typealias PeerEmojiStatus = Int
public typealias TelegramStarRating = Int
public typealias VisualGramGiftCollection = Int
public struct VisualGramGift: Codable, Equatable {
    public enum Direction: String, Codable { case sent, received }
    public var direction: Direction = .sent
    public var counterpartyId: Int64?
    public var date: Int32 = 5
    public var assetIdentifier: String = "test-gift"
    public var identifier: String = "sent:recipient:test-gift"
}
'''

STORE = r'''
public final class VisualGramLocalAppearance {
    private let lock = NSLock()
    var values: [String: VisualGramAppearance] = [:]
    func updateValues(_ change: (inout [String: VisualGramAppearance]) -> Void) { change(&values) }
'''

CHECKS = r'''
let store = VisualGramLocalAppearance()
let own = EnginePeer.Id(10), other = EnginePeer.Id(20), secondAccount = EnginePeer.Id(30)
let gift = VisualGramGift()
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
store.reset(accountId: own)
assert(store.appearance(accountId: own).scheduledGifts?.count == 1, "reset removed another profile's queue")
assert(store.appearance(accountId: own).gifts.isEmpty)
let encoded = try JSONEncoder().encode(store.values)
let restored = try JSONDecoder().decode([String: VisualGramAppearance].self, from: encoded)
let reopened = VisualGramLocalAppearance()
reopened.values = restored
assert(reopened.deliverScheduledGifts(accountId: own, now: 500).count == 1, "pending queue lost on restart")
assert(reopened.appearance(accountId: own, targetPeerId: other).gifts.first?.date == 400)
assert(reopened.appearance(accountId: own).gifts.isEmpty, "wrong profile")
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
print("PASS: delayed delivery, deadline, exactly-once, shared profiles, distinct identities, cross-account editing/reset, v2 migration, reschedule, cancellation and restart")
'''


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="visualgram-delivery-") as folder:
        swift = Path(folder) / "DeliveryTests.swift"
        executable = Path(folder) / "delivery-tests"
        swift.write_text(source(), encoding="utf-8")
        subprocess.run(["xcrun", "swiftc", str(swift), "-o", str(executable)], check=True)
        subprocess.run([str(executable)], check=True)
