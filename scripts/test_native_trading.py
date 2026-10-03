"""Execute the production ownership and local-market transactions as Swift."""
from pathlib import Path
import subprocess
import tempfile
from test_native_upgrade import STUBS


def source():
    root = Path(__file__).resolve().parents[1]
    appearance = (root / 'native/VisualGramLocalAppearance.swift').read_text(encoding='utf-8')
    model = appearance[appearance.index('public struct VisualGramGift:'):appearance.index('    public func displayGift(')] + '}\n'
    management = (root / 'native/VisualGramGiftManagement.swift').read_text(encoding='utf-8')
    reference = management[management.index('    static func isLocalReference('):management.index('    // Read-only preview samples')]
    trading = (root / 'native/VisualGramGiftTrading.swift').read_text(encoding='utf-8')
    trading = trading[:trading.index('    func localMarketState(')] + '}\n'
    return STUBS + model + STORE + reference + '}\n' + trading + CHECKS


STORE = r'''
public struct PeerEmojiStatus: Codable {
    public enum Content: Codable { case starGift(Int64, Int64, String, String, Int64, Int32, Int32, Int32, Int32) }
    var content: Content
}
public struct VisualGramAppearance: Codable {
    var enabled = false
    var gifts: [VisualGramGift] = []
    var stars: Int64?
    var overridesEmojiStatus = false
    var emojiStatus: PeerEmojiStatus?
}
public final class VisualGramLocalAppearance {
    var values: [String: VisualGramAppearance] = [:]
    func snapshotValues() -> [String: VisualGramAppearance] { values }
    func updateValues(_ change: (inout [String: VisualGramAppearance]) -> Void) { change(&values) }
    func appearance(accountId: EnginePeer.Id, targetPeerId: EnginePeer.Id? = nil) -> VisualGramAppearance { values[String((targetPeerId ?? accountId).toInt64())] ?? VisualGramAppearance() }
'''


CHECKS = r'''
func unique(_ id: Int64, _ slug: String) -> StarGift.UniqueGift {
    .init(id: id, giftId: 42, title: "Test", number: 1, slug: slug, owner: .peerId(.init(10)), attributes: [.model(1), .pattern(2), .backdrop(3)], availability: .init(issued: 1, total: 500), giftAddress: nil, resellAmounts: nil, resellForTonOnly: false, releasedBy: nil, valueAmount: nil, valueCurrency: nil, valueUsdAmount: nil, flags: [], themePeerId: nil, peerColor: nil, hostPeerId: nil, minOfferStars: nil, craftChancePermille: nil)
}
let a = EnginePeer.Id(10), b = EnginePeer.Id(20), c = EnginePeer.Id(30)
let store = VisualGramLocalAppearance()
let nft = unique(42, "Test-1")
var local = VisualGramGift(gift: .unique(nft), counterpartyId: 30, date: 100, text: "history")
local.pinnedToTop = true; local.collectionIds = [8]
store.values["10"] = .init(enabled: true, gifts: [local], stars: 100, overridesEmojiStatus: true, emojiStatus: .init(content: .starGift(42, 1, "Test", "Test-1", 2, 0, 0, 0, 0)))
let ref = local.reference(accountId: a)
assert(store.canManageLocalGift(accountId: a, reference: ref))
assert(!store.canManageLocalGift(accountId: b, reference: ref))
assert(!store.transferLocalGift(accountId: b, reference: ref, recipientPeerId: c, now: 200))
assert(!store.transferLocalGift(accountId: a, reference: ref, recipientPeerId: a, now: 200))
assert(store.transferLocalGift(accountId: a, reference: ref, recipientPeerId: b, now: 200))
assert(!store.canManageLocalGift(accountId: a, reference: ref), "old owner retained control")
assert(!store.transferLocalGift(accountId: a, reference: ref, recipientPeerId: c, now: 201), "stale transfer duplicated NFT")
let ownedB = store.appearance(accountId: b).gifts.filter { $0.direction == .received && $0.isHistoryOnly != true }
assert(ownedB.count == 1 && ownedB[0].pinnedToTop == false && ownedB[0].collectionIds == nil && ownedB[0].resaleStars == nil)
assert(ownedB[0].counterpartyId == 10 && ownedB[0].date == 200 && ownedB[0].isTransferred == true)
let aGifts = store.appearance(accountId: a).gifts
assert(aGifts.allSatisfy { $0.isHistoryOnly == true })
assert(aGifts.contains { $0.direction == .sent && $0.counterpartyId == 20 && $0.date == 200 })
assert(store.appearance(accountId: a).emojiStatus == nil && store.appearance(accountId: a).stars == 100)
let bRef = ownedB[0].reference(accountId: b)
assert(store.localReference(slug: "Test-1") == bRef && store.canManageLocalGift(accountId: b, reference: bRef))
assert(!store.listLocalGift(accountId: a, reference: bRef, price: 50))
assert(!store.listLocalGift(accountId: b, reference: bRef, price: -1))
assert(store.listLocalGift(accountId: b, reference: bRef, price: 50))
store.values["30"] = .init(enabled: true, gifts: [], stars: 20)
assert(store.buyLocalGift(accountId: c, recipientPeerId: c, gift: nft, price: 50, requireListing: true, now: 300) == .insufficientBalance)
assert(store.appearance(accountId: c).stars == 20 && store.canManageLocalGift(accountId: b, reference: bRef))
store.values["30"]?.stars = 100
assert(store.buyLocalGift(accountId: c, recipientPeerId: c, gift: nft, price: 60, requireListing: true, now: 300) == .priceChanged)
assert(store.appearance(accountId: c).stars == 100)
assert(store.buyLocalGift(accountId: c, recipientPeerId: c, gift: nft, price: 50, requireListing: true, now: 300) == .success)
assert(store.appearance(accountId: c).stars == 50 && store.appearance(accountId: b).stars == 50)
assert(!store.canManageLocalGift(accountId: b, reference: bRef))
assert(store.appearance(accountId: c).gifts.filter { $0.direction == .received && $0.isHistoryOnly != true }.count == 1)
assert(store.buyLocalGift(accountId: a, recipientPeerId: a, gift: nft, price: 50, requireListing: true, now: 301) == .priceChanged)
let catalog = unique(100, "Catalog-1")
assert(store.buyLocalGift(accountId: a, recipientPeerId: a, gift: catalog, price: 25, requireListing: false, now: 400) == .success)
assert(store.appearance(accountId: a).stars == 75)
assert(store.buyLocalGift(accountId: a, recipientPeerId: a, gift: catalog, price: 25, requireListing: false, now: 401) == .unavailable)
assert(store.appearance(accountId: a).stars == 75)
let data = try JSONEncoder().encode(store.values)
store.values = try JSONDecoder().decode([String: VisualGramAppearance].self, from: data)
assert(store.appearance(accountId: c).stars == 50 && store.localReference(slug: "Test-1") == ownedB[0].reference(accountId: c))
print("PASS: owner-only controls, transfer history and author, stale references, pins, status clearing, listings, atomic local balances, insufficient funds, price changes, duplicate purchases and restart")
'''


if __name__ == '__main__':
    with tempfile.TemporaryDirectory(prefix='visualgram-trading-') as folder:
        swift, executable = Path(folder) / 'TradingTests.swift', Path(folder) / 'trading-tests'
        swift.write_text(source(), encoding='utf-8')
        subprocess.run(['xcrun', 'swiftc', str(swift), '-o', str(executable)], check=True)
        subprocess.run([str(executable)], check=True)
