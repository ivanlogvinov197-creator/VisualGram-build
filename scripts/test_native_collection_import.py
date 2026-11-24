"""Run the production public-gift and username import code with isolated storage."""
from pathlib import Path
import subprocess
import tempfile


def source():
    root = Path(__file__).resolve().parents[1]
    actual = (root / "native/VisualGramCollectionImport.swift").read_text(encoding="utf-8")
    pages = actual[actual.index("public enum VisualGramCollectionImport"):actual.index("    // NETWORK:")] + "}\n"
    methods = actual[actual.index("public extension VisualGramLocalAppearance"):]
    return STUBS + pages + methods + CHECKS


STUBS = r'''
import Foundation
public struct EnginePeer {
    public struct Id: Equatable {
        let value: Int64
        func toInt64() -> Int64 { self.value }
    }
}
public enum StarGift: Codable, Equatable {
    public struct UniqueGift: Codable, Equatable { let slug: String }
    case generic(Int64), unique(UniqueGift)
}
public struct VisualGramUsername: Codable, Equatable {
    var name: String
    var purchaseDate: Int32
    var tonAmount: Int64
    var usdAmount: Int64
}
public struct VisualGramGift: Codable, Equatable {
    enum Direction: Codable { case received, sent }
    var gift: StarGift
    var direction: Direction = .received
    var isHistoryOnly: Bool?
    var identifier = UUID().uuidString
    var collectionSourceKey: String?
    var savedToProfile: Bool?
    var pinnedToTop: Bool?
    init(gift: StarGift, counterpartyId: Int64?, date: Int32, text: String) { self.gift = gift }
}
public struct VisualGramAppearance: Codable, Equatable {
    var enabled = false
    var gifts: [VisualGramGift] = []
    var usernames: [VisualGramUsername] = []
    var giftOrder: [String]?
    var giftOperationHistory: [VisualGramGift]?
}
final class VisualGramActivation {
    static let shared = VisualGramActivation()
    var hasAccess = true
}
public final class VisualGramLocalAppearance {
    var values: [String: VisualGramAppearance] = [:]
    var failWrite = false
    func updateValues(recordOperations: Bool = true, _ transform: (inout [String: VisualGramAppearance]) -> Void) -> Bool {
        guard VisualGramActivation.shared.hasAccess, !self.failWrite else { return false }
        var candidate = self.values
        transform(&candidate)
        self.values = candidate
        return true
    }
    func appearance(accountId: EnginePeer.Id, targetPeerId: EnginePeer.Id) -> VisualGramAppearance {
        self.values[String(targetPeerId.toInt64())] ?? .init()
    }
    static func orderedOwnedGifts(in value: VisualGramAppearance) -> [VisualGramGift] { value.gifts }
    static func giftOperations(in value: VisualGramAppearance) -> [VisualGramGift] { value.giftOperationHistory ?? value.gifts }
}
'''


CHECKS = r'''
let account = EnginePeer.Id(value: 10), target = EnginePeer.Id(value: 20)
let a = VisualGramCollectionImport.Item(gift: .generic(1), date: 100, sourceKey: "user:1")
let b = VisualGramCollectionImport.Item(gift: .generic(1), date: 100, sourceKey: "user:2")
let nft = VisualGramCollectionImport.Item(gift: StarGift.UniqueGift(slug: "Bear-1"), date: 100)
let duplicateNFT = VisualGramCollectionImport.Item(gift: StarGift.UniqueGift(slug: "BEAR-1"), date: 100)
var pages = VisualGramCollectionImport.Pages()
let next = try pages.append([a, nft], nextOffset: "next")
assert(next == "next")
let end = try pages.append([a, b, duplicateNFT], nextOffset: nil)
assert(end == nil)
assert(pages.items.count == 3 && pages.items.map(\.sourceKey) == ["saved:user:1", "unique:bear-1", "saved:user:2"])
let store = VisualGramLocalAppearance()
assert(store.importPublicCollection(accountId: account, targetPeerId: target, items: pages.items) == 3)
let profile = store.values["20"]!
assert(profile.gifts.count == 3 && Set(profile.gifts.map(\.identifier)).count == 3)
assert(profile.gifts[0].gift == .generic(1) && profile.gifts[2].gift == .generic(1))
assert(profile.giftOperationHistory?.isEmpty == true && store.values["10"] == nil)
assert(store.importPublicCollection(accountId: account, targetPeerId: target, items: [b, a, duplicateNFT]) == 0)
let restored = VisualGramLocalAppearance()
restored.values = try JSONDecoder().decode([String: VisualGramAppearance].self, from: JSONEncoder().encode(store.values))
assert(restored.importPublicCollection(accountId: account, targetPeerId: target, items: pages.items) == 0)
assert(restored.importPublicUsernames(accountId: account, targetPeerId: target,
    names: ["Alice", "ALICE", "Other_name", "AlreadyHere", "@@bad", ""], existingNames: ["alreadyhere"], now: 123) == 2)
let names = restored.values["20"]!.usernames
assert(names.map(\.name) == ["Alice", "Other_name"] && names.allSatisfy { $0.tonAmount == 0 && $0.usdAmount == 0 })
assert(restored.importPublicUsernames(accountId: account, targetPeerId: target, names: ["alice", "other_name"], existingNames: [], now: 124) == 0)
restored.failWrite = true
assert(restored.importPublicCollection(accountId: account, targetPeerId: target, items: [VisualGramCollectionImport.Item(gift: .generic(2), date: 101, sourceKey: "user:3")]) == nil)
assert(restored.importPublicUsernames(accountId: account, targetPeerId: target, names: ["NewName"], existingNames: [], now: 125) == nil)
VisualGramActivation.shared.hasAccess = false
assert(store.importPublicCollection(accountId: account, targetPeerId: target, items: [a]) == nil)
assert(store.importPublicUsernames(accountId: account, targetPeerId: target, names: ["NewName"], existingNames: [], now: 125) == nil)
print("PASS public gift and username imports, distinct ordinary copies, pagination, duplicates, persistence, failed writes and access")
'''


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="duckgram-collection-") as folder:
        swift = Path(folder) / "CollectionImportTests.swift"
        executable = Path(folder) / "collection-import-tests"
        swift.write_text(source(), encoding="utf-8")
        subprocess.run(["xcrun", "swiftc", str(swift), "-o", str(executable)], check=True)
        subprocess.run([str(executable)], check=True)

