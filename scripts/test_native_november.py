"""Execute production GRAM and crafting transactions with deterministic randomness."""
from pathlib import Path
import subprocess
import tempfile
import test_native_trading as trading


def source():
    root = Path(__file__).resolve().parents[1]
    base = trading.source().split('func unique(')[0]
    base = base.replace('var stars: Int64?', 'var stars: Int64?\n    var grams: Int64?\n    var gramStarsPerUnit: Int64?\n    var gramHistory: [VisualGramGift.StarsTransaction]?')
    wallet = (root / 'native/VisualGramWallet.swift').read_text(encoding='utf-8')
    wallet = wallet[:wallet.index('    func displayWalletCard(')] + wallet[wallet.index('    func giftForLocalPurchase('):]
    wallet = '\n'.join(line for line in wallet.splitlines() if not line.startswith('import '))
    craft = (root / 'native/VisualGramGiftCrafting.swift').read_text(encoding='utf-8')
    craft = '\n'.join(line for line in craft.splitlines() if not line.startswith('import '))
    return base + '\n' + 'public enum CraftStarGiftError { case generic, unavailable, craftFailed, tooEarly(Int32) }\n' + wallet + '\n' + craft + CHECKS


CHECKS = r'''
func nft(_ id: Int64, chance: Int32? = 500, grams: Int64? = nil, tonOnly: Bool = false, type: Int64 = 42, ownerId: EnginePeer.Id = .init(10)) -> StarGift.UniqueGift {
    .init(id: id, giftId: type, title: "Gift", number: Int32(id), slug: "Gift-\(id)", owner: .peerId(ownerId), attributes: [.model(1), .pattern(2), .backdrop(3)], availability: .init(issued: 1, total: 1000), giftAddress: nil, resellAmounts: [CurrencyAmount(amount: .init(value: grams ?? 100, nanos: 0), currency: grams == nil ? .stars : .ton)], resellForTonOnly: tonOnly, releasedBy: nil, valueAmount: nil, valueCurrency: nil, valueUsdAmount: nil, flags: [], themePeerId: nil, peerColor: nil, hostPeerId: nil, minOfferStars: nil, craftChancePermille: chance)
}
let a = EnginePeer.Id(10), b = EnginePeer.Id(20)
let store = VisualGramLocalAppearance()
let first = VisualGramGift(gift: .unique(nft(1)), counterpartyId: 20, date: 50, text: "old")
let second = VisualGramGift(gift: .unique(nft(2)), counterpartyId: 20, date: 50, text: "old")
let refs = [first.reference(accountId: a), second.reference(accountId: a)]
let attributes: [StarGift.UniqueGift.Attribute] = [.model("Craft", 99, 1, true), .pattern(2), .backdrop(3)]
let probabilities: [[Int32]] = [[90], [80, 200], [70, 190, 460], [60, 180, 450, 1000]]
store.values["10"] = .init(enabled: true, gifts: [first, second], stars: 100)
assert(VisualGramLocalAppearance.parseGrams("0,252") == 252000000)
assert(VisualGramLocalAppearance.parseGrams("0.000000001") == 1)
assert(VisualGramLocalAppearance.parseGrams("1.0000000001") == nil)
assert(VisualGramLocalAppearance.parseGrams("9223372037") == nil)
assert(VisualGramLocalAppearance.parseGrams("-1") == nil)
store.values["10"]?.gramStarsPerUnit = 80
assert(store.localGramPrice(accountId: a, gift: nft(7)) == nil, "Stars-only lot acquired a GRAM quote")
assert(store.giftForLocalPurchase(accountId: a, gift: nft(7)) == nft(7), "invented price was added")
assert(store.localGramPrice(accountId: a, gift: nft(7, grams: 1250000000)) == 1250000000)
func countOwned() -> Int { store.appearance(accountId: a).gifts.filter { $0.direction == .received && $0.isHistoryOnly != true }.count }
if case .failure(.unavailable) = store.craftLocalGifts(accountId: a, references: [refs[0], refs[0]], attributes: attributes, attributePermilles: probabilities, now: 100) {} else { assertionFailure("duplicate inputs") }
assert(countOwned() == 2)
if case .failure(.unavailable) = store.craftLocalGifts(accountId: b, references: refs, attributes: attributes, attributePermilles: probabilities, now: 100) {} else { assertionFailure("wrong owner") }
assert(countOwned() == 2)
if case .failure(.unavailable) = store.craftLocalGifts(accountId: a, references: refs, attributes: [.pattern(2)], attributePermilles: probabilities, now: 100) {} else { assertionFailure("missing model") }
assert(countOwned() == 2)
store.values["10"]?.gifts[0].canCraftAt = 5000
if case let .failure(.tooEarly(date)) = store.craftLocalGifts(accountId: a, references: refs, attributes: attributes, attributePermilles: probabilities, now: 1000) {
    assert(date == 5000, "native date formatter needs the absolute unlock time")
} else { assertionFailure("early craft consumed locked gifts") }
assert(countOwned() == 2)
store.values["10"]?.gifts[0].canCraftAt = nil
store.values["10"]?.gifts[0].purchaseGrams = 250000000
if case let .success(result) = store.craftLocalGifts(accountId: a, references: refs, attributes: attributes, attributePermilles: probabilities, now: 100, random: { $0.lowerBound }) {
    assert(result.isCrafted == true && result.gift != first.gift && result.savedToProfile == true)
    assert(result.purchaseGrams == nil && result.purchaseStars == nil)
    assert(countOwned() == 1)
    if case let .unique(gift) = result.gift { assert(gift.id == 1 && gift.craftChancePermille == nil && gift.attributes[0] == attributes[0]) }
} else { assertionFailure("guaranteed craft did not succeed") }
assert(store.appearance(accountId: a).gifts.filter { $0.isHistoryOnly == true }.count == 2)
assert(store.craftableLocalGifts(accountId: a, giftId: 42, now: 101).isEmpty)
if case .failure(.unavailable) = store.craftLocalGifts(accountId: a, references: refs, attributes: attributes, attributePermilles: probabilities, now: 101) {} else { assertionFailure("replayed craft") }
store.values["10"] = .init(enabled: true, gifts: [first], stars: 100)
if case .failure(.craftFailed) = store.craftLocalGifts(accountId: a, references: [refs[0]], attributes: attributes, attributePermilles: probabilities, now: 100, random: { $0.upperBound - 1 }) {} else { assertionFailure("forced failure") }
assert(countOwned() == 0 && store.appearance(accountId: a).stars == 100)
store.values["10"] = .init(enabled: true, gifts: [], stars: 100)
store.values["10"]?.grams = 2_000_000_000; store.values["10"]?.gramStarsPerUnit = 80
assert(store.buyLocalGiftWithGrams(accountId: a, recipientPeerId: a, gift: nft(7, grams: 1_250_000_000), price: 1_250_000_000, requireListing: false, now: 200) == .success)
assert(store.appearance(accountId: a).grams == 750_000_000 && store.appearance(accountId: a).stars == 100)
assert(store.appearance(accountId: a).gramHistory?.last?.amount == -1_250_000_000)
assert(store.appearance(accountId: a).gifts.last?.purchaseGrams == 1_250_000_000)
assert(store.buyLocalGiftWithGrams(accountId: a, recipientPeerId: a, gift: nft(8, grams: 1_250_000_000), price: 1_250_000_000, requireListing: false, now: 201) == .insufficientBalance)
store.values["10"]?.grams = 10_000_000_000
assert(store.buyLocalGiftWithGrams(accountId: a, recipientPeerId: a, gift: nft(7, grams: 1_250_000_000), price: 1_250_000_000, requireListing: false, now: 202) == .unavailable)
assert(store.appearance(accountId: a).grams == 10_000_000_000)
let data = try JSONEncoder().encode(store.values)
store.values = try JSONDecoder().decode([String: VisualGramAppearance].self, from: data)
assert(store.appearance(accountId: a).grams == 10_000_000_000 && store.appearance(accountId: a).gifts.last?.purchaseGrams == 1_250_000_000)
store.beforeUpdate = { store.values["10"]?.gramStarsPerUnit = 40 }
assert(store.buyLocalGiftWithGrams(accountId: a, recipientPeerId: a, gift: nft(9), price: 1_250_000_000, requireListing: false, now: 203) == .priceChanged)
assert(store.appearance(accountId: a).grams == 10_000_000_000 && store.appearance(accountId: a).gramHistory?.count == 1, "stale quote changed the balance or history")
let gramMarket = VisualGramLocalAppearance(), c = EnginePeer.Id(30)
gramMarket.values["10"] = .init(enabled: true, gifts: [], stars: 100)
gramMarket.values["10"]?.grams = 2_500_000_000; gramMarket.values["10"]?.gramStarsPerUnit = 80
for sellerId in [b, c] {
    var listed = VisualGramGift(gift: .unique(nft(25, ownerId: sellerId)), counterpartyId: nil, date: 100, text: "")
    listed.resaleGrams = 1_250_000_000
    gramMarket.values[String(sellerId.toInt64())] = .init(enabled: true, gifts: [listed], stars: 0)
    gramMarket.values[String(sellerId.toInt64())]?.grams = 0
}
assert(gramMarket.buyLocalGiftWithGrams(accountId: a, recipientPeerId: a, gift: nft(25, grams: 1_250_000_000, ownerId: c), price: 1_250_000_000, requireListing: true, now: 400) == .success)
assert(gramMarket.appearance(accountId: a).grams == 1_250_000_000 && gramMarket.appearance(accountId: b).grams == 0 && gramMarket.appearance(accountId: c).grams == 1_250_000_000)
assert(gramMarket.appearance(accountId: a).stars == 100)
let eligibility = VisualGramLocalAppearance()
var lockedInput = VisualGramGift(gift: .unique(nft(32)), counterpartyId: nil, date: 100, text: "")
lockedInput.canCraftAt = 5000
var consumedInput = VisualGramGift(gift: .unique(nft(33)), counterpartyId: nil, date: 100, text: "")
consumedInput.isHistoryOnly = true
let noChanceInput = VisualGramGift(gift: .unique(nft(34, chance: nil)), counterpartyId: nil, date: 100, text: "")
eligibility.values["10"] = .init(enabled: true, gifts: [first, lockedInput, consumedInput, noChanceInput])
assert(eligibility.craftableLocalGifts(accountId: a, giftId: 42, now: 1000).map { $0.identifier } == [first.identifier])
assert(Set(eligibility.craftableLocalGifts(accountId: a, giftId: 42, now: 5000).map { $0.identifier }) == Set([first.identifier, lockedInput.identifier]))
let layout = VisualGramGift.CardPlacement(x: .infinity, y: -40, scale: .nan, angle: .infinity).normalized
assert(layout.x == 50 && layout.y == 0 && layout.scale == 1 && layout.angle == 0)
let orderStore = VisualGramLocalAppearance()
var newer = second; newer.date = first.date + 10
assert(VisualGramLocalAppearance.orderedOwnedGifts(in: .init(enabled: true, gifts: [first, newer])).map { $0.identifier } == [second.identifier, first.identifier], "default order disagrees with native profile")
var pinned = first; pinned.pinnedToTop = true
orderStore.values["10"] = .init(enabled: true, gifts: [pinned, second])
assert(orderStore.saveGiftOrder(accountId: a, targetPeerId: a, identifiers: [second.identifier, first.identifier]))
assert(orderStore.appearance(accountId: a).giftOrder == [first.identifier, second.identifier], "pinned gifts lost their leading positions")
assert(!orderStore.saveGiftOrder(accountId: a, targetPeerId: a, identifiers: [first.identifier, first.identifier]))
orderStore.values["10"]?.gifts.append(VisualGramGift(gift: .unique(nft(99)), counterpartyId: nil, date: 100, text: ""))
assert(!orderStore.saveGiftOrder(accountId: a, targetPeerId: a, identifiers: [first.identifier, second.identifier]), "stale editor overwrote a new gift")
let clones = VisualGramLocalAppearance()
let ownClone = VisualGramGift(gift: .unique(nft(77)), counterpartyId: nil, date: 100, text: "")
let otherClone = VisualGramGift(gift: .unique(nft(77)), counterpartyId: nil, date: 100, text: "")
clones.values["10"] = .init(enabled: true, gifts: [ownClone])
clones.values["20"] = .init(enabled: true, gifts: [otherClone])
assert(clones.localCraftReference(accountId: a, gift: nft(77)) == ownClone.reference(accountId: a))
assert(clones.localCraftReference(accountId: b, gift: nft(77)) == otherClone.reference(accountId: b))
clones.values["10"]?.gifts[0].isHistoryOnly = true
assert(clones.localCraftReference(accountId: a, gift: nft(77)) == nil, "craft fell back to another profile's duplicate")
let metadata = VisualGramLocalAppearance()
var legacy = VisualGramGift(gift: .unique(nft(55, chance: nil)), counterpartyId: 20, date: 123, text: "local text")
legacy.resaleStars = 200
metadata.values["10"] = .init(enabled: true, gifts: [legacy])
metadata.updateLocalCraftMetadata(accountId: a, reference: legacy.reference(accountId: a), gift: nft(55))
assert(metadata.craftableLocalGifts(accountId: a, giftId: 42, now: 1000).count == 1, "legacy gift never became craftable")
assert(metadata.appearance(accountId: a).gifts[0].text == "local text" && metadata.appearance(accountId: a).gifts[0].resaleStars == 200)
metadata.values["10"]?.gifts[0].isHistoryOnly = true
metadata.updateLocalCraftMetadata(accountId: a, reference: legacy.reference(accountId: a), gift: nft(55, chance: nil))
assert(metadata.appearance(accountId: a).gifts[0].craftChance == 500, "late refresh touched consumed history")

let dual = VisualGramLocalAppearance()
dual.values["10"] = .init(enabled: true, gifts: [], stars: 900)
dual.values["10"]?.grams = 3_000_000_000
let quote = dual.giftForLocalPurchase(accountId: a, gift: nft(801), starsPerGram: Decimal(80))
assert(quote.resellAmounts?.first(where: { $0.currency == .ton })?.amount.value == 1_250_000_000)
assert(!quote.resellForTonOnly)
assert(dual.buyLocalGiftWithGrams(accountId: a, recipientPeerId: a, gift: nft(801), price: 1_250_000_000, requireListing: false, now: 1000, starsPerGram: Decimal(80), text: "Caption", nameHidden: false, entities: [1, 2]) == .success)
assert(dual.appearance(accountId: a).grams == 1_750_000_000 && dual.appearance(accountId: a).stars == 900)
assert(dual.appearance(accountId: a).gifts.last?.text == "Caption" && dual.appearance(accountId: a).gifts.last?.nameHidden == false)
assert(dual.appearance(accountId: a).gifts.last?.textEntities == [1, 2])
let gramOnly = nft(802, grams: 1_250_000_000, tonOnly: true)
assert(dual.buyLocalGift(accountId: a, recipientPeerId: a, gift: gramOnly, price: 100, requireListing: false, now: 1001) == .unavailable)
assert(dual.appearance(accountId: a).stars == 900)
assert(dual.giftForLocalPurchase(accountId: a, gift: gramOnly, starsPerGram: Decimal(80)).resellForTonOnly)
let historyStore = VisualGramLocalAppearance()
var historic = VisualGramAppearance(enabled: true, gifts: [first])
VisualGramLocalAppearance.recordGiftOperations(previous: nil, value: &historic)
assert(historic.giftOperationHistory?.count == 1)
let receiptId = historic.giftOperationHistory![0].identifier
let previousHistory = historic
historic.gifts.append(second)
VisualGramLocalAppearance.recordGiftOperations(previous: previousHistory, value: &historic)
assert(historic.giftOperationHistory?.count == 2)
let savedHistory = historic
VisualGramLocalAppearance.recordGiftOperations(previous: savedHistory, value: &historic)
assert(historic.giftOperationHistory?.count == 2, "metadata update duplicated operation history")
assert(historic.giftOperationHistory?.first?.operationUndo == nil, "legacy history unexpectedly fabricated undo data")
historyStore.values["10"] = historic
assert(historyStore.editGiftDetails(accountId: a, targetPeerId: a, identifier: second.identifier, history: false, counterpartyId: 30, date: 123456789, text: "edited"))
assert(historyStore.appearance(accountId: a).gifts.last?.gift == second.gift && historyStore.appearance(accountId: a).gifts.last?.text == "edited")
let senderStore = VisualGramLocalAppearance()
var outgoing = VisualGramGift(gift: .unique(nft(901)), counterpartyId: b.toInt64(), direction: .sent, date: 90, text: "hello")
senderStore.addGift(accountId: a, targetPeerId: a, gift: outgoing)
assert(senderStore.appearance(accountId: a).gifts.first?.isHistoryOnly == true)
assert(senderStore.appearance(accountId: b).gifts.first?.direction == .received && senderStore.appearance(accountId: b).gifts.first?.text == "hello")
assert(senderStore.editGiftDetails(accountId: a, targetPeerId: a, identifier: outgoing.identifier, history: true, counterpartyId: 30, date: 92, text: "moved") == false, "gift ID was confused with operation ID")
assert(senderStore.editGiftDetails(accountId: a, targetPeerId: b, identifier: outgoing.identifier, history: false, counterpartyId: 10, date: 93, text: "changed"))
assert(senderStore.appearance(accountId: a).gifts.first?.date == 93 && senderStore.appearance(accountId: b).gifts.first?.date == 93)
assert(senderStore.editGiftDetails(accountId: a, targetPeerId: b, identifier: outgoing.identifier, history: false, counterpartyId: 20, date: 94, text: "self"))
assert(senderStore.appearance(accountId: b).gifts.count == 1 && senderStore.appearance(accountId: b).gifts.first?.direction == .received, "editing sender to self replaced ownership with outgoing history")
assert(senderStore.appearance(accountId: a).gifts.isEmpty)

// A supported regular gift remains craftable after its local upgrade.
let upgradedCollection = nft(704, chance: 220)
let regular = StarGift.Gift(id: 42, title: "Cake", availability: .init(total: 1000), releasedBy: nil)
let preview = StarGiftUpgradePreview(attributes: [.model(1), .pattern(2), .backdrop(3)])
let upgraded = VisualGramLocalAppearance.makeUpgradedGift(regular, preview: preview, ownerId: a, template: upgradedCollection)!
assert(upgraded.slug == upgradedCollection.slug && upgraded.number == upgradedCollection.number && upgraded.craftChancePermille == 220)
assert(!upgraded.slug.contains("-0000-"))
let upgradedStore = VisualGramLocalAppearance()
let upgradedLocal = VisualGramGift(gift: .unique(upgraded), counterpartyId: nil, date: 100, text: "caption")
upgradedStore.values["10"] = .init(enabled: true, gifts: [upgradedLocal])
assert(upgradedStore.craftableLocalGifts(accountId: a, giftId: 42, now: 1000).count == 1)
let upgradedReference = upgradedLocal.reference(accountId: a)
if case .success = upgradedStore.craftLocalGifts(accountId: a, references: [upgradedReference], attributes: attributes, attributePermilles: probabilities, now: 1000, random: { _ in 0 }) {} else { assertionFailure("local upgrade could not craft") }
// Repair saved UUID gifts in place, preserving identity, caption and ownership.
var legacyUpgrade = VisualGramLocalAppearance.makeUpgradedGift(regular, preview: preview, ownerId: a)!
legacyUpgrade = .init(id: legacyUpgrade.id, giftId: 42, title: "Cake", number: 2, slug: "Gift-54941C57-D6A3-4134-9865-18E63E8378DF", owner: .peerId(a), attributes: legacyUpgrade.attributes, availability: legacyUpgrade.availability, giftAddress: nil, resellAmounts: nil, resellForTonOnly: false, releasedBy: nil, valueAmount: nil, valueCurrency: nil, valueUsdAmount: nil, flags: [], themePeerId: nil, peerColor: nil, hostPeerId: nil, minOfferStars: nil, craftChancePermille: nil)
let legacyLocal = VisualGramGift(gift: .unique(legacyUpgrade), counterpartyId: 20, date: 100, text: "kept")
let repairStore = VisualGramLocalAppearance(); repairStore.values["10"] = .init(enabled: true, gifts: [legacyLocal])
repairStore.updateLocalCraftMetadata(accountId: a, reference: legacyLocal.reference(accountId: a), gift: upgradedCollection)
assert(repairStore.appearance(accountId: a).gifts[0].identifier == legacyLocal.identifier)
assert(repairStore.appearance(accountId: a).gifts[0].text == "kept" && repairStore.appearance(accountId: a).gifts[0].craftChance == 220)
if case let .unique(repaired) = repairStore.appearance(accountId: a).gifts[0].gift { assert(repaired.id == legacyUpgrade.id && repaired.slug == upgradedCollection.slug) }
var resetCard = VisualGramAppearance(enabled: true, gifts: [first], stars: 123)
resetCard.grams = 999; resetCard.gramCardGiftIds = [first.identifier]; resetCard.gramCardBackgroundId = first.identifier
resetCard.gramCardPlacements = [first.identifier: .init(x: 50, y: 50)]
VisualGramLocalAppearance.resetGramCard(in: &resetCard)
assert(resetCard.gifts == [first] && resetCard.stars == 123 && resetCard.grams == 999)
assert(resetCard.gramCardGiftIds == [] && resetCard.gramCardBackgroundId == nil && resetCard.gramCardPlacements?.isEmpty == true)
var secondCopy = first; secondCopy.localIdentifier = "another-copy"
assert(VisualGramLocalAppearance.cardStickerAddress(first) != VisualGramLocalAppearance.cardStickerAddress(secondCopy), "two local copies shared sticker hit-test identity")

let money = VisualGramLocalAppearance()
assert(money.localGramBalance(accountId: a) == nil)
assert(money.topUpLocalGrams(accountId: a, amount: 1_000_000_001, now: 1))
assert(money.transferLocalGrams(accountId: a, to: b, amount: 100_000_001, comment: "test", now: 2) == .sent)
assert(money.localGramBalance(accountId: a) == 900_000_000 && money.localGramBalance(accountId: b) == 100_000_001)
let outgoing = money.appearance(accountId: a).gramHistory!.last!
let incoming = money.appearance(accountId: b).gramHistory!.last!
assert(outgoing.id == incoming.id && outgoing.amount == -incoming.amount && outgoing.comment == "test")
assert(outgoing.peerId == b.toInt64() && incoming.peerId == a.toInt64() && outgoing.kind == .transfer)
assert(money.transferLocalGrams(accountId: a, to: a, amount: 1, comment: nil, now: 3) == .invalidRecipient)
assert(money.transferLocalGrams(accountId: a, to: b, amount: 900_000_001, comment: nil, now: 3) == .insufficientBalance)
assert(!money.topUpLocalGrams(accountId: a, amount: Int64.max, now: 3))
money.values["20"]?.grams = Int64.max
assert(money.transferLocalGrams(accountId: a, to: b, amount: 1, comment: nil, now: 4) == .overflow)
assert(money.localGramBalance(accountId: a) == 900_000_000 && money.appearance(accountId: a).gramHistory?.count == 2)
assert(money.appearance(accountId: b).gramHistory?.count == 1)
money.beforeUpdate = { money.values["10"]?.grams = 0 }
assert(money.transferLocalGrams(accountId: a, to: b, amount: 1, comment: nil, now: 4) == .insufficientBalance)
let savedMoney = try! JSONDecoder().decode(VisualGramAppearance.self, from: JSONEncoder().encode(money.appearance(accountId: a)))
assert(savedMoney.gramHistory?.last?.comment == "test")
let oldGramEntry = #"{"id":"old","date":1,"amount":100,"kind":"topUp"}"#.data(using: .utf8)!
assert(try! JSONDecoder().decode(VisualGramGift.StarsTransaction.self, from: oldGramEntry).comment == nil)

print("PASS: GRAM precision, overflow, local transfers, paired history, strict quote currency, stale/insufficient balance, persistence; craft consumption, retained history, unlock date, owner and replay guards")
'''


if __name__ == '__main__':
    with tempfile.TemporaryDirectory(prefix='visualgram-november-') as folder:
        swift, executable = Path(folder) / 'NovemberTests.swift', Path(folder) / 'november-tests'
        swift.write_text(source(), encoding='utf-8')
        subprocess.run(['xcrun', 'swiftc', str(swift), '-o', str(executable)], check=True)
        subprocess.run([str(executable)], check=True)
