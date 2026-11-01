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
func nft(_ id: Int64, chance: Int32? = 500, type: Int64 = 42, ownerId: EnginePeer.Id = .init(10)) -> StarGift.UniqueGift {
    .init(id: id, giftId: type, title: "Gift", number: Int32(id), slug: "Gift-\(id)", owner: .peerId(ownerId), attributes: [.model(1), .pattern(2), .backdrop(3)], availability: .init(issued: 1, total: 1000), giftAddress: nil, resellAmounts: [CurrencyAmount(amount: .init(value: 100, nanos: 0), currency: .stars)], resellForTonOnly: false, releasedBy: nil, valueAmount: nil, valueCurrency: nil, valueUsdAmount: nil, flags: [], themePeerId: nil, peerColor: nil, hostPeerId: nil, minOfferStars: nil, craftChancePermille: chance)
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
assert(store.localGramPrice(accountId: a, gift: nft(7)) == 1250000000)
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
assert(store.buyLocalGiftWithGrams(accountId: a, recipientPeerId: a, gift: nft(7), price: 1_250_000_000, requireListing: false, now: 200) == .success)
assert(store.appearance(accountId: a).grams == 750_000_000 && store.appearance(accountId: a).stars == 100)
assert(store.appearance(accountId: a).gramHistory?.last?.amount == -1_250_000_000)
assert(store.appearance(accountId: a).gifts.last?.purchaseGrams == 1_250_000_000)
assert(store.buyLocalGiftWithGrams(accountId: a, recipientPeerId: a, gift: nft(8), price: 1_250_000_000, requireListing: false, now: 201) == .insufficientBalance)
store.values["10"]?.grams = 10_000_000_000
assert(store.buyLocalGiftWithGrams(accountId: a, recipientPeerId: a, gift: nft(7), price: 1_250_000_000, requireListing: false, now: 202) == .unavailable)
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
    listed.resaleStars = 100
    gramMarket.values[String(sellerId.toInt64())] = .init(enabled: true, gifts: [listed], stars: 0)
    gramMarket.values[String(sellerId.toInt64())]?.grams = 0
}
assert(gramMarket.buyLocalGiftWithGrams(accountId: a, recipientPeerId: a, gift: nft(25, ownerId: c), price: 1_250_000_000, requireListing: true, now: 400) == .success)
assert(gramMarket.appearance(accountId: a).grams == 1_250_000_000 && gramMarket.appearance(accountId: b).grams == 0 && gramMarket.appearance(accountId: c).grams == 1_250_000_000)
assert(gramMarket.appearance(accountId: a).stars == 100)
print("PASS: GRAM precision/overflow, conversion, debit/history, duplicate/insufficient balance, persistence; craft success/failure/consumption, retained history, unlock date, owner and replay guards")
'''


if __name__ == '__main__':
    with tempfile.TemporaryDirectory(prefix='visualgram-november-') as folder:
        swift, executable = Path(folder) / 'NovemberTests.swift', Path(folder) / 'november-tests'
        swift.write_text(source(), encoding='utf-8')
        subprocess.run(['xcrun', 'swiftc', str(swift), '-o', str(executable)], check=True)
        subprocess.run([str(executable)], check=True)
