"""Exercise the actual Swift upgrade transaction with lightweight engine types."""
from pathlib import Path
import subprocess
import tempfile


def source():
    root = Path(__file__).resolve().parents[1]
    appearance = (root / "native/VisualGramLocalAppearance.swift").read_text(encoding="utf-8")
    management = (root / "native/VisualGramGiftManagement.swift").read_text(encoding="utf-8")
    model = appearance[appearance.index("public struct VisualGramGift:"):appearance.index("    public func displayGift(")] + "}\n"
    reference = management[management.index("    static func isLocalReference("):management.index("    @discardableResult\n    func updateGift(")]
    return STUBS + model + STORE + reference + "}\n" + CHECKS


STUBS = r'''
import Foundation
public enum EnginePeer {
    public struct Id: Codable, Hashable {
        let value: Int64
        public init(_ value: Int64) { self.value = value }
        public func toInt64() -> Int64 { self.value }
    }
}
public enum EngineMessage {
    public struct Id: Hashable { let peerId: EnginePeer.Id; let namespace: Int32; let id: Int32 }
}
public enum StarGiftReference: Equatable { case message(messageId: EngineMessage.Id) }
public enum StarGift: Codable, Equatable {
    public struct Gift: Codable, Equatable {
        public struct Availability: Codable, Equatable { let total: Int32 }
        let id: Int64; let title: String?; let availability: Availability?; let releasedBy: EnginePeer.Id?
    }
    public struct UniqueGift: Codable, Equatable {
        public enum Owner: Codable, Equatable { case peerId(EnginePeer.Id) }
        public struct Availability: Codable, Equatable { let issued: Int32; let total: Int32 }
        public enum Attribute: Codable, Equatable {
            public enum AttributeType { case model, pattern, backdrop }
            case model(Int), pattern(Int), backdrop(Int)
            var attributeType: AttributeType {
                switch self { case .model: return .model; case .pattern: return .pattern; case .backdrop: return .backdrop }
            }
        }
        let id: Int64; let giftId: Int64; let title: String; let number: Int32; let slug: String
        let owner: Owner?; let attributes: [Attribute]; let availability: Availability
        let giftAddress: String?; let resellAmounts: [Int]?; let resellForTonOnly: Bool
        let releasedBy: EnginePeer.Id?; let valueAmount: Int64?; let valueCurrency: String?; let valueUsdAmount: Int64?
        let flags: [Int]; let themePeerId: EnginePeer.Id?; let peerColor: Int?; let hostPeerId: EnginePeer.Id?
        let minOfferStars: Int64?; let craftChancePermille: Int32?
    }
    case generic(Gift), unique(UniqueGift)
}
public struct StarGiftUpgradePreview { let attributes: [StarGift.UniqueGift.Attribute] }
public enum ProfileGiftsContext {
    public enum State {
        public struct StarGift { let gift: SwiftGift; let reference: StarGiftReference; let owner: EnginePeer.Id }
    }
}
public typealias SwiftGift = StarGift
public extension VisualGramGift {
    func profileGift(accountId: EnginePeer.Id, sender: EnginePeer?) -> ProfileGiftsContext.State.StarGift {
        return .init(gift: self.gift, reference: self.reference(accountId: accountId), owner: accountId)
    }
}
'''

STORE = r'''
public struct VisualGramAppearance: Codable { var gifts: [VisualGramGift] = [] }
public final class VisualGramLocalAppearance {
    var values: [Int64: VisualGramAppearance] = [:]
    func appearance(accountId: EnginePeer.Id, targetPeerId: EnginePeer.Id? = nil) -> VisualGramAppearance { values[(targetPeerId ?? accountId).toInt64()] ?? VisualGramAppearance() }
    func update(accountId: EnginePeer.Id, targetPeerId: EnginePeer.Id, change: (inout VisualGramAppearance) -> Void) {
        var value = appearance(accountId: accountId, targetPeerId: targetPeerId)
        change(&value); values[targetPeerId.toInt64()] = value
    }
'''

CHECKS = r'''
let owner = EnginePeer.Id(10), viewer = EnginePeer.Id(20)
let store = VisualGramLocalAppearance()
var original = VisualGramGift(gift: .generic(.init(id: 42, title: "Sample Gift", availability: .init(total: 500), releasedBy: nil)), counterpartyId: 30, date: 100, text: "caption")
original.pinnedToTop = true; original.savedToProfile = true; original.collectionIds = [8]
store.values[10] = .init(gifts: [original])
let reference = original.reference(accountId: owner)
let attributes: [StarGift.UniqueGift.Attribute] = [.model(1), .model(2), .pattern(3), .pattern(4), .backdrop(5), .backdrop(6)]
assert(store.upgradeLocalGift(accountId: viewer, reference: reference, preview: .init(attributes: [.model(1)]), keepOriginalInfo: true) == nil, "incomplete preview upgraded")
assert(store.localGift(accountId: viewer, reference: reference)?.gift == original.gift)
let result = store.upgradeLocalGift(accountId: viewer, reference: reference, preview: .init(attributes: attributes), keepOriginalInfo: false)!
assert(result.owner == owner && result.reference == reference, "owner or stable reference changed")
let upgraded = store.localGift(accountId: viewer, reference: reference)!
assert(upgraded.identifier == original.identifier && upgraded.pinnedToTop == true && upgraded.collectionIds == [8] && upgraded.savedToProfile == true)
assert(upgraded.counterpartyId == 30 && upgraded.date == 100 && upgraded.text == "caption", "history metadata lost")
assert(upgraded.hidesOriginalInfo == true)
if case let .unique(unique) = upgraded.gift {
    assert(unique.owner == .peerId(owner) && unique.giftId == 42 && unique.number >= 1 && unique.number <= 500)
    assert(unique.attributes.count == 3 && unique.attributes.allSatisfy { attributes.contains($0) })
} else { assertionFailure("not upgraded") }
assert(store.appearance(accountId: viewer).gifts.isEmpty, "viewer identity received owner's gift")
assert(store.upgradeLocalGift(accountId: owner, reference: reference, preview: .init(attributes: attributes), keepOriginalInfo: true) == nil, "upgraded twice")
let data = try JSONEncoder().encode(store.values)
store.values = try JSONDecoder().decode([Int64: VisualGramAppearance].self, from: data)
assert(store.localGift(accountId: viewer, reference: reference)?.gift == upgraded.gift, "upgrade lost after restart")
var combinations = Set<String>()
for _ in 0..<100 {
    store.values[10] = .init(gifts: [original])
    let random = store.upgradeLocalGift(accountId: viewer, reference: reference, preview: .init(attributes: attributes), keepOriginalInfo: true)!
    if case let .unique(unique) = random.gift { combinations.insert(String(describing: unique.attributes)) }
}
assert(combinations.count > 1, "all random results identical")
original.direction = .sent; store.values[10] = .init(gifts: [original])
assert(store.upgradeLocalGift(accountId: viewer, reference: original.reference(accountId: owner), preview: .init(attributes: attributes), keepOriginalInfo: true) == nil, "outgoing gift upgraded in sender's profile")
print("PASS: random supported attributes, incomplete preview, owner, stable references, history, pins, collections, restart and single upgrade")
'''


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="visualgram-upgrade-") as folder:
        swift = Path(folder) / "UpgradeTests.swift"
        executable = Path(folder) / "upgrade-tests"
        swift.write_text(source(), encoding="utf-8")
        subprocess.run(["xcrun", "swiftc", str(swift), "-o", str(executable)], check=True)
        subprocess.run([str(executable)], check=True)
