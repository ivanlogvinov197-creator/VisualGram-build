"""Execute the production tab gesture and Stars history renderer as Swift."""
from pathlib import Path
import subprocess
import tempfile


def source():
    root = Path(__file__).resolve().parents[1]
    appearance = (root / 'native/VisualGramLocalAppearance.swift').read_text(encoding='utf-8')
    model = appearance[appearance.index('public struct VisualGramGift:'):appearance.index('    public enum Direction:')] + '}\n'
    counter = (root / 'native/VisualGramTabTapCounter.swift').read_text(encoding='utf-8')
    renderer = (root / 'native/VisualGramStarsHistory.swift').read_text(encoding='utf-8')
    renderer = '\n'.join(line for line in renderer.splitlines() if not line.startswith('import '))
    return STUBS + model + counter + renderer + CHECKS


STUBS = r'''
import Foundation
public struct EnginePeer: Equatable {
    public struct Id: Hashable { public let value: Int64; public init(_ value: Int64) { self.value = value }; public func toInt64() -> Int64 { value } }
    public let id: Id
}
public enum StarGift: Codable, Equatable { case generic(Int64), unique(Int64) }
public struct StarsAmount { public let value: Int64; public let nanos: Int32 }
public struct CurrencyAmount { public enum Currency { case stars }; public let amount: StarsAmount; public let currency: Currency }
public enum StarsTransactionsContext { public enum Mode { case all, incoming, outgoing } }
public enum StarsContext { public enum State {
    public struct Transaction {
        public struct Flags: OptionSet { public var rawValue: Int32; public init(rawValue: Int32) { self.rawValue = rawValue }; public static let isStarGiftResale = Flags(rawValue: 512) }
        public enum Peer: Equatable { case peer(EnginePeer), premiumBot }
        public let flags: Flags; public let id: String; public let count: CurrencyAmount; public let date: Int32; public let peer: Peer; public let title: String?; public let starGift: StarGift?
        public init(flags: Flags, id: String, count: CurrencyAmount, date: Int32, peer: Peer, title: String?, description: Any?, photo: Any?, transactionDate: Any?, transactionUrl: Any?, paidMessageId: Any?, giveawayMessageId: Any?, media: [Int], subscriptionPeriod: Any?, starGift: StarGift?, floodskipNumber: Any?, starrefCommissionPermille: Any?, starrefPeerId: Any?, starrefAmount: Any?, paidMessageCount: Any?, premiumGiftMonths: Any?, adsProceedsFromDate: Any?, adsProceedsToDate: Any?) {
            self.flags = flags; self.id = id; self.count = count; self.date = date; self.peer = peer; self.title = title; self.starGift = starGift
        }
    }
} }
public struct VisualGramAppearance { public var starsHistory: [VisualGramGift.StarsTransaction]? }
public final class VisualGramLocalAppearance {
    public var values: [Int64: VisualGramAppearance] = [:]
    public func appearance(accountId: EnginePeer.Id) -> VisualGramAppearance { values[accountId.toInt64()] ?? .init() }
}
'''

CHECKS = r'''
var taps = VisualGramTabTapCounter()
assert(!taps.tap(now: 1.0) && !taps.tap(now: 1.2) && taps.tap(now: 1.4))
assert(!taps.tap(now: 1.5), "third tap didn't consume/reset sequence")
assert(!taps.tap(now: 4.0) && !taps.tap(now: 4.2))
taps.reset()
assert(!taps.tap(now: 4.4), "another tab failed to reset sequence")
assert(!taps.tap(now: 2.0) && !taps.tap(now: 2.1) && taps.tap(now: 2.2), "clock reset was not handled")
let a = EnginePeer.Id(10), b = EnginePeer.Id(20)
let store = VisualGramLocalAppearance()
let history: [VisualGramGift.StarsTransaction] = [
    .init(id: "topup", date: 100, amount: 100, kind: .topUp, title: nil, peerId: nil, gift: nil),
    .init(id: "transfer", date: 300, amount: -25, kind: .transfer, title: nil, peerId: 20, gift: .unique(7)),
    .init(id: "purchase", date: 200, amount: -50, kind: .purchase, title: nil, peerId: 20, gift: .unique(8)),
    .init(id: "sale", date: 400, amount: 75, kind: .sale, title: nil, peerId: 20, gift: .unique(9))
]
store.values[10] = .init(starsHistory: history)
let peers = [Int64(10): EnginePeer(id: a), Int64(20): EnginePeer(id: b)]
let all = store.starsHistoryTransactions(accountId: a, mode: .all, peers: peers)
assert(all.map { $0.date } == [400, 300, 200, 100], "history is not sorted by operation date")
assert(all.map { $0.count.amount.value }.reduce(0, +) == 100)
assert(Set(all.map { $0.id }).count == 4 && all[1].id == "vg-stars:transfer")
assert(all[1].peer == .peer(EnginePeer(id: b)) && !all[1].flags.contains(.isStarGiftResale))
assert(all[2].flags.contains(.isStarGiftResale) && all[0].flags.contains(.isStarGiftResale))
assert(store.starsHistoryTransactions(accountId: a, mode: .incoming, peers: peers).map { $0.count.amount.value } == [75, 100])
assert(store.starsHistoryTransactions(accountId: a, mode: .outgoing, peers: peers).map { $0.count.amount.value } == [-25, -50])
assert(store.starsHistoryTransactions(accountId: b, mode: .all, peers: peers).isEmpty)
let encoded = try JSONEncoder().encode(history)
let decoded = try JSONDecoder().decode([VisualGramGift.StarsTransaction].self, from: encoded)
assert(decoded == history)
print("PASS: triple Chats tap/reset/timeout, Stars history native amounts, dates, peers, resale/transfer distinction, mode filters, account isolation and persistence")
'''

if __name__ == '__main__':
    with tempfile.TemporaryDirectory(prefix='visualgram-stars-') as folder:
        swift, executable = Path(folder) / 'StarsHistoryTests.swift', Path(folder) / 'stars-history-tests'
        swift.write_text(source(), encoding='utf-8')
        subprocess.run(['xcrun', 'swiftc', str(swift), '-o', str(executable)], check=True)
        subprocess.run([str(executable)], check=True)
