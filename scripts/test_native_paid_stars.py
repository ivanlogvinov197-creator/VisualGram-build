"""Compile the production visual Stars ledger and graph with lightweight engine types."""
from pathlib import Path
import subprocess
import tempfile


def source():
    root = Path(__file__).resolve().parents[1] / "native"
    appearance = (root / "VisualGramLocalAppearance.swift").read_text(encoding="utf-8")
    history_model = appearance[appearance.index("public struct VisualGramGift:"):appearance.index("    public enum Direction:")] + "}\n"
    method_start = appearance.index("    @discardableResult\n    func updateValues(")
    update = appearance[method_start:appearance.index("    public func reset(", method_start)]
    wallet = (root / "VisualGramWallet.swift").read_text(encoding="utf-8")
    history = wallet[wallet.index("public enum VisualGramBalanceHistory:"):wallet.index("public extension VisualGramLocalAppearance")]
    trading = (root / "VisualGramGiftTrading.swift").read_text(encoding="utf-8")
    record = trading[trading.index("    static func recordStarsTransaction"):trading.index("    func localReference")]
    raw = (root / "VisualGramPaidStars.swift").read_text(encoding="utf-8")
    actions = "\n".join(line for line in raw.splitlines() if not line.startswith("import "))
    return STUBS + history_model + history + "extension VisualGramLocalAppearance {\n" + update + record + "}\n" + actions + "\n" + CHECKS


STUBS = r'''
import Foundation
public typealias MessageTextEntity = Int
public enum StarGift: Codable, Equatable { case sample }
public enum TelegramPaidReactionPrivacy: Equatable {
    case `default`, anonymous, peer(EnginePeer.Id)
}
enum Namespaces {
    enum Peer {
        static let CloudUser: Int32 = 0
        static let CloudChannel: Int32 = 2
    }
    enum Message { static let Cloud: Int32 = 0 }
}
public struct EnginePeer {
    public struct Id: Equatable {
        let value: Int64
        init(_ value: Int64) { self.value = value }
        var namespace: Int32 { self.value < 0 ? 2 : 0 }
        func toInt64() -> Int64 { self.value }
    }
}
public struct EngineMessage {
    public struct Id {
        let peerId: EnginePeer.Id
        let namespace: Int32
        let id: Int32
    }
}
public struct MessageReaction {
    enum Reaction { case stars, other }
    let value: Reaction
    var count: Int32
    let chosenOrder: Int?
}
public final class ReactionsMessageAttribute {
    public struct TopPeer {
        var peerId: EnginePeer.Id?
        var count: Int32
        var isTop: Bool
        var isMy: Bool
        var isAnonymous: Bool
    }
    let canViewList: Bool
    let reactions: [MessageReaction]
    let recentPeers: [Int]
    let topPeers: [Int]

    init(canViewList: Bool, isTags: Bool, reactions: [MessageReaction], recentPeers: [Int], topPeers: [Int]) {
        self.canViewList = canViewList
        self.reactions = reactions
        self.recentPeers = recentPeers
        self.topPeers = topPeers
    }
}
final class PendingStarsReactionsMessageAttribute {}
public struct Message {
    let attributes: [Any]
    let stableVersion: UInt32
    func withUpdatedAttributes(_ attributes: [Any]) -> Message { .init(attributes: attributes, stableVersion: self.stableVersion) }
    func withUpdatedStableVersion(stableVersion: UInt32) -> Message { .init(attributes: self.attributes, stableVersion: stableVersion) }
}
public enum StatsGraph { case Loaded(token: String?, data: String) }
public struct VisualGramAppearance: Codable, Equatable {
    var enabled = true
    var stars: Int64?
    var paidChatMessages: [String: [VisualGramPaidChatMessage]]?
    var paidPostReactions: [String: Int32]?
    var paidReactionPrivacy: [String: Int64]?
    var starsHistory: [VisualGramGift.StarsTransaction]?
    var gramHistory: [VisualGramGift.StarsTransaction]?
    var starsHistoryOrder: [String]?
    var gramHistoryOrder: [String]?
}
final class VisualGramActivation {
    static let shared = VisualGramActivation()
    var allowed = true
    func authorizesAppearance() -> Bool { self.allowed }
}
enum Queue {
    static func mainQueue() -> Self { .main }
    case main
    func async(_ f: () -> Void) { f() }
}
struct Revision { func set(_ value: Int) {} }
public final class VisualGramLocalAppearance {
    var values: [String: VisualGramAppearance] = [:]
    var allowWrite = true
    var vaultKey: Data? = Data()
    let lock = NSLock()
    var revisionValue = 0
    let revision = Revision()

    func appearance(accountId: EnginePeer.Id) -> VisualGramAppearance {
        self.values[String(accountId.toInt64())] ?? .init()
    }
    func writeProtectedValues(_ candidate: [String: VisualGramAppearance]) -> Bool { self.allowWrite }
    func update(accountId: EnginePeer.Id, _ transform: (inout VisualGramAppearance) -> Void) {
        self.updateValues { values in
            let key = String(accountId.toInt64())
            var profile = values[key] ?? .init()
            transform(&profile)
            values[key] = profile
        }
    }
    static func recordGiftOperations(previous: [String: VisualGramAppearance], values: inout [String: VisualGramAppearance]) {}
}
'''


CHECKS = r'''
let account = EnginePeer.Id(10)
let user = EnginePeer.Id(20)
let post = EngineMessage.Id(peerId: .init(-1), namespace: 0, id: 10)
let otherPost = EngineMessage.Id(peerId: .init(-2), namespace: 0, id: 10)
let now: Int32 = 1_700_000_000
let store = VisualGramLocalAppearance()
store.values["10"] = .init(stars: 30)
store.values["20"] = .init(stars: 100)
let initial = store.values

func send(_ price: Int64) -> VisualGramStarsSpendResult {
    store.sendVisualPaidMessages(accountId: account, peerId: user, messages: [("Part 1", [4]), ("Part 2", [])], price: price, now: now)
}

assert(send(Int64.max) == .unavailable)
assert(send(16) == .insufficientBalance)
store.allowWrite = false
assert(send(5) == .unavailable && store.values == initial)
store.allowWrite = true
VisualGramActivation.shared.allowed = false
assert(send(5) == .unavailable && store.values == initial)
VisualGramActivation.shared.allowed = true
assert(send(5) == .saved && store.values["10"]?.stars == 20 && store.values["20"]?.stars == 100)
let messages = store.values["10"]!.paidChatMessages!["20"]!
assert(messages.map(\.text) == ["Part 1", "Part 2"] && messages.first?.entities == [4])
assert(messages[0].messageId < messages[1].messageId && messages[1].messageId < -(1 << 30))
assert(store.values["10"]?.starsHistory?.map(\.amount) == [-10])

assert(store.addVisualPaidReaction(accountId: account, messageId: post, count: 21, now: now) == .insufficientBalance)
assert(store.addVisualPaidReaction(accountId: account, messageId: post, count: 10, now: now) == .saved)
assert(store.addVisualPaidReaction(accountId: account, messageId: post, count: 10, now: now) == .saved)
assert(store.addVisualPaidReaction(accountId: account, messageId: post, count: 1, now: now) == .insufficientBalance)
assert(store.visualPaidReactionCount(accountId: account, messageId: post) == 20)
assert(store.visualPaidReactionCount(accountId: account, messageId: otherPost) == 0)
assert(store.visualPaidReactionCount(accountId: user, messageId: post) == 0)
assert(store.values["10"]?.starsHistory?.map(\.amount) == [-10, -10, -10])
let data = try JSONEncoder().encode(store.values)
let reopened = VisualGramLocalAppearance()
reopened.values = try JSONDecoder().decode([String: VisualGramAppearance].self, from: data)
assert(reopened.values == store.values)
assert(reopened.visualReactionPrivacy(accountId: account, messageId: post) == .default)
store.setVisualReactionPrivacy(accountId: account, messageId: post, privacy: .anonymous)
assert(store.visualReactionPrivacy(accountId: account, messageId: post) == .anonymous)
let leader = ReactionsMessageAttribute.TopPeer(peerId: user, count: 40, isTop: true, isMy: false, isAnonymous: false)
let top = store.visualReactionTopPeers(accountId: account, messageId: post, existing: [leader])
assert(top.count == 2 && top[1].count == 20 && top[1].isMy && top[1].isAnonymous && top[1].peerId == nil)
store.setVisualReactionPrivacy(accountId: account, messageId: post, privacy: .peer(user))
let changed = store.visualReactionTopPeers(accountId: account, messageId: post, existing: [leader])
assert(changed[1].peerId == user && !changed[1].isAnonymous && store.values["10"]?.stars == 0)

let originalReaction = ReactionsMessageAttribute(canViewList: true, isTags: false, reactions: [.init(value: .stars, count: 12, chosenOrder: nil), .init(value: .other, count: 3, chosenOrder: 0)], recentPeers: [1], topPeers: [2])
let original = Message(attributes: [originalReaction], stableVersion: 1)
let rendered = VisualGramLocalAppearance.displayingVisualPaidReaction(original, count: 20)
let renderedReaction = rendered.attributes.first as! ReactionsMessageAttribute
assert(renderedReaction.reactions.map(\.count) == [32, 3] && renderedReaction.recentPeers == [1] && renderedReaction.topPeers == [2])
assert(originalReaction.reactions.map(\.count) == [12, 3] && rendered.stableVersion != original.stableVersion)
let pending = Message(attributes: [originalReaction, PendingStarsReactionsMessageAttribute()], stableVersion: 1)
assert(VisualGramLocalAppearance.displayingVisualPaidReaction(pending, count: 20).stableVersion == pending.stableVersion)

var statsProfile = store.values["10"]!
statsProfile.starsHistory?.append(.init(id: "credit", date: now - 1, amount: 500, kind: .topUp, title: nil, peerId: nil, gift: nil))
statsProfile.starsHistory?.append(.init(id: "old", date: now - 366 * 86_400, amount: 300, kind: .topUp, title: nil, peerId: nil, gift: nil))
statsProfile.starsHistory?.append(.init(id: "future", date: now + 1, amount: 100, kind: .topUp, title: nil, peerId: nil, gift: nil))
let stats = VisualGramStarsStatistics(appearance: statsProfile, now: now)!
assert(stats.balance == 0 && stats.received == 800 && stats.spent == 30 && stats.operations == 5)
guard case let .Loaded(_, chartJSON)? = stats.incomingGraph else { fatalError("Expected daily chart") }
let chart = try JSONSerialization.jsonObject(with: Data(chartJSON.utf8)) as! [String: Any]
let columns = chart["columns"] as! [[Any]]
assert(columns.count == 2 && columns.allSatisfy { $0.count == 366 })
assert(columns[1].dropFirst().compactMap { $0 as? Int }.reduce(0, +) == 500)
assert(VisualGramStarsStatistics(appearance: .init(stars: 0), now: now)?.incomingGraph == nil)
assert(VisualGramStarsStatistics(appearance: .init(stars: nil), now: now) == nil)
print("PASS: visual Stars atomic spending, isolated chat/reaction records, history, and daily chart")
'''


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="visualgram-paid-stars-") as folder:
        swift = Path(folder) / "PaidStarsTests.swift"
        executable = Path(folder) / "paid-stars-tests"
        swift.write_text(source(), encoding="utf-8")
        subprocess.run(["xcrun", "swiftc", str(swift), "-o", str(executable)], check=True)
        subprocess.run([str(executable)], check=True)

