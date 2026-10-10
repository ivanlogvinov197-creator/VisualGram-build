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
    imports = management[management.index('    func addGift('):management.index('    func scheduleGift(')]
    upgraded = management[management.index('    static func makeUpgradedGift('):management.index('    @discardableResult\n    func updateGift(')]
    visibility = management[management.index('    func profileState('):management.index('    func collection(')]
    trading = (root / 'native/VisualGramGiftTrading.swift').read_text(encoding='utf-8')
    trading = trading[:trading.index('    func localMarketState(')] + '}\n'
    return STUBS + model + STORE + reference + imports + upgraded + visibility + '}\n' + trading + CHECKS + PURCHASE_CHECKS


STORE = r'''
public struct PeerEmojiStatus: Codable {
    public enum Content: Codable { case starGift(Int64, Int64, String, String, Int64, Int32, Int32, Int32, Int32) }
    var content: Content
}
public struct VisualGramAppearance: Codable {
    var enabled = false
    var premium = false
    var gifts: [VisualGramGift] = []
    var stars: Int64?
    var giftPurchaseCounts: [String: Int32]?
    var starsHistory: [VisualGramGift.StarsTransaction]?
    var overridesEmojiStatus = false
    var emojiStatus: PeerEmojiStatus?
}
public final class VisualGramLocalAppearance {
    var values: [String: VisualGramAppearance] = [:]
    func snapshotValues() -> [String: VisualGramAppearance] { values }
    func updateValues(_ change: (inout [String: VisualGramAppearance]) -> Void) { change(&values) }
    func appearance(accountId: EnginePeer.Id, targetPeerId: EnginePeer.Id? = nil) -> VisualGramAppearance { values[String((targetPeerId ?? accountId).toInt64())] ?? VisualGramAppearance() }
    func update(accountId: EnginePeer.Id, targetPeerId: EnginePeer.Id? = nil, _ change: (inout VisualGramAppearance) -> Void) { let key = String((targetPeerId ?? accountId).toInt64()); var value = values[key] ?? VisualGramAppearance(); change(&value); values[key] = value }
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
assert(store.appearance(accountId: a).emojiStatus == nil && store.appearance(accountId: a).stars == 75)
assert(store.appearance(accountId: a).starsHistory?.last?.amount == -25)
let afterFee = store.appearance(accountId: a).starsHistory?.count
assert(!store.transferLocalGift(accountId: a, reference: ref, recipientPeerId: c, now: 201))
assert(store.appearance(accountId: a).stars == 75 && store.appearance(accountId: a).starsHistory?.count == afterFee)
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
assert(store.appearance(accountId: c).starsHistory?.last?.amount == -50 && store.appearance(accountId: b).starsHistory?.last?.amount == 50)
assert(!store.canManageLocalGift(accountId: b, reference: bRef))
assert(store.appearance(accountId: c).gifts.filter { $0.direction == .received && $0.isHistoryOnly != true }.count == 1)
assert(store.buyLocalGift(accountId: a, recipientPeerId: a, gift: nft, price: 50, requireListing: true, now: 301) == .priceChanged)
let catalog = unique(100, "Catalog-1")
assert(store.buyLocalGift(accountId: a, recipientPeerId: a, gift: catalog, price: 25, requireListing: false, now: 400) == .success)
assert(store.appearance(accountId: a).stars == 50)
assert(store.appearance(accountId: a).gifts.last?.counterpartyId == 10 && store.appearance(accountId: a).gifts.last?.purchaseStars == 25)
assert(store.buyLocalGift(accountId: a, recipientPeerId: a, gift: catalog, price: 25, requireListing: false, now: 401) == .unavailable)
assert(store.appearance(accountId: a).stars == 50)
let data = try JSONEncoder().encode(store.values)
store.values = try JSONDecoder().decode([String: VisualGramAppearance].self, from: data)
assert(store.appearance(accountId: c).stars == 50 && store.localReference(slug: "Test-1") == ownedB[0].reference(accountId: c))
print("PASS: owner-only controls, transfer history and author, stale references, pins, status clearing, listings, atomic local balances, insufficient funds, price changes, duplicate purchases and restart")
'''


PURCHASE_CHECKS = r'''
let purchases = VisualGramLocalAppearance()
purchases.values["10"] = .init(enabled: true, gifts: [], stars: 100)
var bear = StarGift.Gift(id: 7, title: "Bear", availability: nil, releasedBy: nil)
func buyBear(_ gift: StarGift.Gift, upgrade: Bool = false, preview: StarGiftUpgradePreview? = nil) -> VisualGramGiftPurchaseResult {
    purchases.buyLocalOrdinaryGift(accountId: a, recipientPeerId: b, gift: gift, text: "caption", includeUpgrade: upgrade, preview: preview, now: 1000)
}
assert(buyBear(bear) == .success && buyBear(bear) == .success)
assert(purchases.appearance(accountId: a).stars == 70)
let receivedBears = purchases.appearance(accountId: b).gifts
assert(receivedBears.count == 2 && receivedBears[0].identifier != receivedBears[1].identifier)
assert(receivedBears.allSatisfy { $0.counterpartyId == 10 && $0.purchaseStars == 15 && $0.purchaseBuyerId == 10 && $0.text == "caption" })
let sentBears = purchases.appearance(accountId: a).gifts
assert(sentBears.count == 2 && sentBears.allSatisfy { $0.direction == .sent && $0.counterpartyId == 20 })
assert(Set(sentBears.map { $0.identifier }) == Set(receivedBears.map { $0.identifier }))
if case let .message(messageId) = receivedBears[0].reference(accountId: b) {
    assert(purchases.localReference(messageId: messageId) == receivedBears[0].reference(accountId: b), "chat resolved the sender's history instead of the active owner")
}
var sold = bear; sold.soldOut = true
assert(buyBear(sold) == .unavailable)
var exhausted = bear; exhausted.availability = .init(remains: 0, total: 100)
assert(buyBear(exhausted) == .unavailable)
var locked = bear; locked.lockedUntilDate = 2000
assert(buyBear(locked) == .unavailable)
var auction = bear; auction.flags = .isAuction
assert(buyBear(auction) == .unavailable)
var limited = StarGift.Gift(id: 8, title: "Limited", availability: .init(remains: 2, total: 5), releasedBy: nil)
limited.perUserLimit = .init(total: 1, remains: 1)
assert(buyBear(limited) == .success && buyBear(limited) == .unavailable)
let before = purchases.appearance(accountId: a).stars
var expensive = bear; expensive.price = Int64.max
assert(buyBear(expensive) == .invalid)
expensive.price = 100
assert(buyBear(expensive) == .insufficientBalance && purchases.appearance(accountId: a).stars == before)
assert(buyBear(bear, upgrade: true, preview: .init(attributes: [.model(1)])) == .unavailable)
let preview = StarGiftUpgradePreview(attributes: [.model(1), .pattern(2), .backdrop(3)])
assert(buyBear(bear, upgrade: true, preview: preview) == .success)
if case let .unique(value) = purchases.appearance(accountId: b).gifts.last!.gift { assert(value.owner == .peerId(b) && value.giftId == bear.id) } else { assertionFailure("prepaid upgrade did not create NFT") }
assert(purchases.appearance(accountId: b).gifts.last?.purchaseStars == 20)
let transferredPurchase = store.appearance(accountId: c).gifts.first { $0.isHistoryOnly != true }!
assert(transferredPurchase.purchaseStars == 50 && transferredPurchase.purchaseBuyerId == 30)
let hidden = receivedBears[0]
purchases.values["20"]?.gifts[0].savedToProfile = false
let viewerState = purchases.profileState(.init(), accountId: a, peerId: b, collectionId: nil)
let ownerState = purchases.profileState(.init(), accountId: b, peerId: b, collectionId: nil)
assert(!viewerState.gifts.contains { $0.reference == hidden.reference(accountId: b) })
assert(!viewerState.filteredGifts.contains { $0.reference == hidden.reference(accountId: b) })
assert(ownerState.gifts.contains { $0.reference == hidden.reference(accountId: b) }, "owner lost hidden gift")
let order = purchases.appearance(accountId: b).gifts.map { $0.identifier }
assert(purchases.moveGift(accountId: a, targetPeerId: b, identifier: order[1], offset: -1))
assert(purchases.appearance(accountId: b).gifts[0].identifier == order[1])
assert(!purchases.moveGift(accountId: a, targetPeerId: b, identifier: order[1], offset: -1))
assert(VisualGramLocalAppearance.nftSlugs(from: "https://t.me/nft/PlushPepe-1?x=1\nPlushPepe-2, PlushPepe-1") == ["PlushPepe-1", "PlushPepe-2"])
assert(VisualGramLocalAppearance.nftSlugs(from: "https://example.com/nft/PlushPepe-1") == nil)
assert(VisualGramLocalAppearance.nftSlugs(from: "PlushPepe-1 broken") == nil)
let savedPurchases = try JSONEncoder().encode(purchases.values)
purchases.values = try JSONDecoder().decode([String: VisualGramAppearance].self, from: savedPurchases)
assert(buyBear(limited) == .unavailable, "restart reset purchase limit")
let feeTest = VisualGramLocalAppearance()
feeTest.values["10"] = .init(enabled: true, gifts: [local], stars: 24)
let feeGiftReference = local.reference(accountId: a)
assert(!feeTest.transferLocalGift(accountId: a, reference: feeGiftReference, recipientPeerId: b, now: 500))
assert(feeTest.appearance(accountId: a).stars == 24 && feeTest.canManageLocalGift(accountId: a, reference: feeGiftReference))
assert(feeTest.appearance(accountId: a).starsHistory == nil)
feeTest.values["10"]?.stars = 25
assert(feeTest.transferLocalGift(accountId: a, reference: feeGiftReference, recipientPeerId: b, now: 501))
assert(feeTest.appearance(accountId: a).stars == 0 && feeTest.appearance(accountId: a).starsHistory?.last?.amount == -25)
assert(purchases.appearance(accountId: b).gifts[0].identifier == order[1])
print("PASS: ordinary purchases, duplicate copies, sold-out/auction/date/limit gates, prepaid upgrade, purchase chat metadata, atomic debits, hidden profiles, batch links, reorder and restart")
'''


if __name__ == '__main__':
    with tempfile.TemporaryDirectory(prefix='visualgram-trading-') as folder:
        swift, executable = Path(folder) / 'TradingTests.swift', Path(folder) / 'trading-tests'
        swift.write_text(source(), encoding='utf-8')
        subprocess.run(['xcrun', 'swiftc', str(swift), '-o', str(executable)], check=True)
        subprocess.run([str(executable)], check=True)
