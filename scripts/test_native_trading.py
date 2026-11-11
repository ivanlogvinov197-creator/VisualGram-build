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
    price = management[management.index('    static let localGiftUpgradeStars:'):management.index('    func upgradeLocalGift(')]
    upgraded = price + management[management.index('    static func makeUpgradedGift('):management.index('    @discardableResult\n    func updateGift(')]
    visibility = management[management.index('    func profileState('):management.index('    func collection(')]
    removals = management[management.index('    func removeLocalGifts('):management.index('    func reorderGifts(')]
    trading = (root / 'native/VisualGramGiftTrading.swift').read_text(encoding='utf-8')
    trading = trading[:trading.index('    func localMarketState(')] + '}\n'
    reordering = management[management.index('    static func orderedOwnedGifts('):management.index('    func chatGifts(')]
    premium_model = appearance[appearance.index('public struct VisualGramPremiumGift:'):appearance.index('public struct VisualGramAppearance:')]
    return STUBS + model + premium_model + STORE + reordering + reference + imports + upgraded + removals + visibility + '}\n' + trading + CHECKS + PURCHASE_CHECKS + REMOVAL_CHECKS + SELLER_CHECKS + PREMIUM_CHECKS


STORE = r'''
enum Namespaces { enum Peer { static let CloudUser: Int32 = 0 } }
extension EnginePeer.Id { var namespace: Int32 { 0 } }
public struct PeerEmojiStatus: Codable {
    public enum Content: Codable { case starGift(Int64, Int64, String, String, Int64, Int32, Int32, Int32, Int32) }
    var content: Content
}
public struct VisualGramAppearance: Codable {
    var enabled = false
    var premium = false
    var gifts: [VisualGramGift] = []
    var giftOperationHistory: [VisualGramGift]?
    var premiumGifts: [VisualGramPremiumGift]?
    var giftOrder: [String]?
    var gramCardGiftIds: [String]?
    var gramCardBackgroundId: String?
    var gramCardPlacements: [String: VisualGramGift.CardPlacement]?
    var stars: Int64?
    var giftPurchaseCounts: [String: Int32]?
    var starsHistory: [VisualGramGift.StarsTransaction]?
    var overridesEmojiStatus = false
    var emojiStatus: PeerEmojiStatus?
}
public final class VisualGramLocalAppearance {
    static func editGiftOperationNarrative(_ original: VisualGramGift, profile: Int64, counterparty: Int64?, date: Int32, text: String, values: inout [String: VisualGramAppearance]) {}
    var values: [String: VisualGramAppearance] = [:]
    var beforeUpdate: (() -> Void)?
    func snapshotValues() -> [String: VisualGramAppearance] { values }
    func updateValues(recordOperations: Bool = true, _ change: (inout [String: VisualGramAppearance]) -> Void) { let hook = beforeUpdate; beforeUpdate = nil; hook?(); change(&values) }
    func appearance(accountId: EnginePeer.Id, targetPeerId: EnginePeer.Id? = nil) -> VisualGramAppearance { values[String((targetPeerId ?? accountId).toInt64())] ?? VisualGramAppearance() }
    func update(accountId: EnginePeer.Id, targetPeerId: EnginePeer.Id? = nil, _ change: (inout VisualGramAppearance) -> Void) { let key = String((targetPeerId ?? accountId).toInt64()); var value = values[key] ?? VisualGramAppearance(); change(&value); values[key] = value }
'''

PREMIUM_CHECKS = r'''
let premiumStore = VisualGramLocalAppearance()
premiumStore.values["10"] = .init(enabled: true, stars: 2500)
premiumStore.values["20"] = .init(stars: 100)
assert(premiumStore.buyLocalPremiumGift(accountId: a, recipientPeerId: b, months: 12, price: 2500, text: "Thanks", entities: [3], now: 500) == .success)
let premiumBuyer = premiumStore.appearance(accountId: a)
let premiumRecipient = premiumStore.appearance(accountId: a, targetPeerId: b)
assert(premiumRecipient.enabled && premiumRecipient.premium && premiumRecipient.stars == 100)
assert(premiumStore.appearance(accountId: b).premium && !premiumBuyer.premium)
assert(premiumBuyer.stars == 0 && premiumBuyer.starsHistory?.last?.amount == -2500)
assert(premiumBuyer.premiumGifts?.last?.recipientId == 20 && premiumBuyer.premiumGifts?.last?.months == 12)
assert(premiumBuyer.premiumGifts?.last?.text == "Thanks" && premiumBuyer.premiumGifts?.last?.entities == [3])
assert(premiumStore.buyLocalPremiumGift(accountId: a, recipientPeerId: c, months: 12, price: 2500, text: "", entities: [], now: 501) == .insufficientBalance)
assert(premiumStore.appearance(accountId: a).premiumGifts?.count == 1)
assert(premiumStore.appearance(accountId: a).starsHistory?.count == 1)
assert(!premiumStore.appearance(accountId: c).premium)
let premiumReload = try JSONDecoder().decode([String: VisualGramAppearance].self, from: JSONEncoder().encode(premiumStore.values))
assert(premiumReload["10"]?.premiumGifts == premiumBuyer.premiumGifts && premiumReload["20"]?.premium == true)
print("PASS: local Premium activation for recipient, debit, insufficient funds, caption, history and persistence")
'''


CHECKS = r'''
func unique(_ id: Int64, _ slug: String, ownerId: EnginePeer.Id = .init(10)) -> StarGift.UniqueGift {
    .init(id: id, giftId: 42, title: "Test", number: 1, slug: slug, owner: .peerId(ownerId), attributes: [.model(1), .pattern(2), .backdrop(3)], availability: .init(issued: 1, total: 500), giftAddress: nil, resellAmounts: nil, resellForTonOnly: false, releasedBy: nil, valueAmount: nil, valueCurrency: nil, valueUsdAmount: nil, flags: [], themePeerId: nil, peerColor: nil, hostPeerId: nil, minOfferStars: nil, craftChancePermille: nil)
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
let sentNFT = store.appearance(accountId: a).gifts.first { $0.direction == .sent }!
let recipientLink = store.localGiftLink(accountId: a, reference: sentNFT.reference(accountId: a))!
let recipientSlug = String(recipientLink.split(separator: "/").last!)
assert(store.giftForLocalLink(slug: recipientSlug)?.0 == b)
assert(store.giftForLocalLink(slug: recipientSlug)?.1.identifier == ownedB[0].identifier)
assert(store.localGiftLink(accountId: b, reference: bRef) == recipientLink)
assert(store.giftForLocalLink(slug: "Test-1") == nil)

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
let exhausted = StarGift.Gift(id: bear.id, title: bear.title, availability: .init(remains: 0, total: 100), releasedBy: bear.releasedBy)
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
let previousUpgradeBalance = purchases.appearance(accountId: a).stars!
let preview = StarGiftUpgradePreview(attributes: [.model(1), .pattern(2), .backdrop(3)])
assert(buyBear(bear, upgrade: true, preview: preview) == .success)
if case let .unique(value) = purchases.appearance(accountId: b).gifts.last!.gift { assert(value.owner == .peerId(b) && value.giftId == bear.id) } else { assertionFailure("prepaid upgrade did not create NFT") }
assert(purchases.appearance(accountId: b).gifts.last?.purchaseStars == 40)
assert(purchases.appearance(accountId: a).stars == previousUpgradeBalance - 40)
assert(purchases.appearance(accountId: a).starsHistory?.last?.amount == -25)
assert(purchases.appearance(accountId: a).starsHistory?.last?.title == "Улучшение подарка")
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


REMOVAL_CHECKS = r'''
let cleanup = VisualGramLocalAppearance()
let worn = VisualGramGift(gift: .unique(unique(101, "Test-101")), counterpartyId: 20, date: 100, text: "")
let keep = VisualGramGift(gift: .unique(unique(102, "Test-102")), counterpartyId: 20, date: 100, text: "")
var oldHistory = worn
oldHistory.localIdentifier = "history-only-copy"
oldHistory.isHistoryOnly = true
cleanup.values["10"] = .init(enabled: true, gifts: [oldHistory, worn, keep], giftOrder: [worn.identifier, keep.identifier], gramCardGiftIds: [worn.identifier, keep.identifier], gramCardBackgroundId: worn.identifier, overridesEmojiStatus: true, emojiStatus: .init(content: .starGift(101, 1, "Test", "Test-101", 2, 0, 0, 0, 0)))
cleanup.values["20"] = .init(enabled: true, gifts: [keep])
cleanup.removeLocalGifts(accountId: a, identifiers: [oldHistory.identifier])
assert(cleanup.appearance(accountId: a).emojiStatus != nil, "deleting a history row removed the active NFT status")
cleanup.removeLocalGifts(accountId: a, identifiers: [worn.identifier])
let cleaned = cleanup.appearance(accountId: a)
assert(cleaned.emojiStatus == nil && cleaned.overridesEmojiStatus)
assert(cleaned.gifts.map { $0.identifier } == [keep.identifier])
assert(cleaned.giftOrder == [keep.identifier] && cleaned.gramCardGiftIds == [keep.identifier] && cleaned.gramCardBackgroundId == nil)
assert(cleanup.appearance(accountId: b).gifts.count == 1, "deletion leaked into another profile")
print("PASS: gift deletion clears worn status, card decorations and order; deleting history preserves an active status")
'''

SELLER_CHECKS = r'''
let overlap = VisualGramLocalAppearance()
var copyB = VisualGramGift(gift: .unique(unique(203, "Test-203", ownerId: b)), counterpartyId: nil, date: 100, text: "")
var copyC = VisualGramGift(gift: .unique(unique(203, "Test-203", ownerId: c)), counterpartyId: nil, date: 100, text: "")
copyB.resaleStars = 40; copyC.resaleStars = 60
overlap.values["10"] = .init(enabled: true, gifts: [], stars: 100)
overlap.values["20"] = .init(enabled: true, gifts: [copyB], stars: 5)
overlap.values["30"] = .init(enabled: true, gifts: [copyC], stars: 5)
assert(overlap.buyLocalGift(accountId: a, recipientPeerId: a, gift: unique(203, "Test-203"), price: 60, requireListing: true, now: 300) == .unavailable, "ambiguous seller was picked by dictionary order")
assert(overlap.appearance(accountId: a).stars == 100)
assert(overlap.buyLocalGift(accountId: a, recipientPeerId: a, gift: unique(203, "Test-203", ownerId: c), price: 60, requireListing: true, now: 301) == .success)
assert(overlap.appearance(accountId: a).stars == 40 && overlap.appearance(accountId: b).stars == 5 && overlap.appearance(accountId: c).stars == 65)
assert(overlap.appearance(accountId: b).gifts.contains { $0.isHistoryOnly != true }, "purchase consumed another profile's visual copy")
let offers = VisualGramLocalAppearance.uniqueMarketOffers([copyB.gift, copyC.gift, .unique(unique(204, "Test-204")), .generic(bear), .generic(bear)])
assert(offers.count == 4 && offers[0] == copyB.gift, "duplicate NFT identity leaked into the market grid or ordinary copies were merged")
print("PASS: overlapping visual NFT copies select the displayed seller and never a random profile")
'''


if __name__ == '__main__':
    with tempfile.TemporaryDirectory(prefix='visualgram-trading-') as folder:
        swift, executable = Path(folder) / 'TradingTests.swift', Path(folder) / 'trading-tests'
        swift.write_text(source(), encoding='utf-8')
        subprocess.run(['xcrun', 'swiftc', str(swift), '-o', str(executable)], check=True)
        subprocess.run([str(executable)], check=True)
