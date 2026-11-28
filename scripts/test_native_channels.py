"""Compile the production channel model and shared appearance transaction."""
from pathlib import Path
import subprocess
import tempfile


def source():
    native = Path(__file__).resolve().parents[1] / "native"
    model = (native / "VisualGramChannels.swift").read_text(encoding="utf-8")
    model = "\n".join(line for line in model.splitlines() if line != "import Postbox")
    appearance = (native / "VisualGramLocalAppearance.swift").read_text(encoding="utf-8")
    field = next(line for line in appearance.splitlines() if line.startswith("    var visualChannels:"))
    read = appearance[appearance.index("    public func appearance("):appearance.index("    public func update(accountId:")]
    start = appearance.index("    @discardableResult\n    func updateValues(")
    transaction = appearance[start:appearance.index("    public static func chatGiftHash(", start)]
    menu = (native / "VisualGramChannelsMenu.swift").read_text(encoding="utf-8")
    query = menu[menu.index("private enum VisualGramChannelQuery"):menu.index("private enum VisualGramChannelsAction")]
    imports = (native / "VisualGramCollectionImport.swift").read_text(encoding="utf-8")
    start = imports.index("    public static func username(")
    username = imports[start:imports.index("\n    }", start) + 6]
    return (STUBS.replace("__CHANNEL_FIELD__", field) + read + transaction + "}\n" + model +
            "\nenum VisualGramCollectionImport {\n" + username + "\n}\n" + query + CHECKS)


STUBS = r'''
import Foundation

enum Namespaces {
    enum Peer {
        static let CloudUser: Int32 = 0
        static let CloudChannel: Int32 = 2
    }
}
public enum EnginePeer {
    public struct Id: Equatable, Sendable {
        let value: Int64
        init(_ value: Int64) { self.value = value }
        var namespace: Int32 { self.value < 0 ? Namespaces.Peer.CloudChannel : Namespaces.Peer.CloudUser }
        func toInt64() -> Int64 { self.value }
    }
}
public struct VisualGramAppearance: Codable, Equatable {
    var enabled = false
    var scheduledGifts: [Schedule]?
    var hiddenChatGifts: [String: Set<String>]?
__CHANNEL_FIELD__
    var profileChannelId: Int64?

    struct Schedule: Codable, Equatable { let targetPeerId: Int64 }
}
final class VisualGramActivation {
    static let shared = VisualGramActivation()
    var allowed = true
    func authorizesAppearance() -> Bool { self.allowed }
}
enum Queue {
    case main
    static func mainQueue() -> Self { .main }
    func async(_ f: () -> Void) { f() }
}
struct Revision { func set(_ value: Int) {} }
public final class VisualGramLocalAppearance: @unchecked Sendable {
    let lock = NSLock()
    var values: [String: VisualGramAppearance]
    var vaultKey: Data? = Data()
    var revisionValue = 0
    let revision = Revision()
    var allowWrites = true
    var persisted: Data?
    init(_ values: [String: VisualGramAppearance] = [:]) { self.values = values }
    func writeProtectedValues(_ values: [String: VisualGramAppearance]) -> Bool {
        guard self.allowWrites, let encoded = try? JSONEncoder().encode(values) else { return false }
        self.persisted = encoded
        return true
    }
    static func recordGiftOperations(previous: [String: VisualGramAppearance], values: inout [String: VisualGramAppearance]) {
        fatalError("Channel writes must not run the gift journal")
    }
'''


CHECKS = r'''
assert(VisualGramChannelQuery(" @Duck_Channel ") == .username("Duck_Channel"))
assert(VisualGramChannelQuery("1234567890") == .id(1234567890))
assert(VisualGramChannelQuery("-1001234567890") == .id(1234567890))
for invalid in ["0", "-1000000000000", "-1234", "-9223372036854775808", "9223372036854775807", "@bad!"] {
    assert(VisualGramChannelQuery(invalid) == nil)
}
let account = EnginePeer.Id(1), other = EnginePeer.Id(2)
let source = EnginePeer.Id(-100123), additional = EnginePeer.Id(-100456), user = EnginePeer.Id(3)
let initial = VisualGramChannelProperties(title: "Original", about: "Description", username: " @Actual ", subscriberCount: 420)
let legacy = try JSONDecoder().decode([String: VisualGramAppearance].self, from: Data(#"{"1":{"enabled":true}}"#.utf8))
let store = VisualGramLocalAppearance(legacy)
assert(store.profileChannel(accountId: account) == nil)
assert(!store.setProfileChannel(accountId: account, channelId: user, replacing: nil))
assert(store.setProfileChannel(accountId: account, channelId: source, replacing: nil))
assert(store.profileChannel(accountId: other) == nil)
let reopenedProfile = VisualGramLocalAppearance(try JSONDecoder().decode([String: VisualGramAppearance].self, from: store.persisted!))
assert(reopenedProfile.profileChannel(accountId: account) == source)
assert(!store.setProfileChannel(accountId: account, channelId: additional, replacing: nil))
store.allowWrites = false
assert(!store.setProfileChannel(accountId: account, channelId: additional, replacing: source))
assert(store.profileChannel(accountId: account) == source)
store.allowWrites = true
assert(store.setProfileChannel(accountId: account, channelId: nil, replacing: source))
assert(store.profileChannel(accountId: account) == nil)

assert(store.visualChannels(accountId: account).isEmpty)
assert(!store.copyVisualChannel(accountId: account, sourcePeerId: user, initial: initial))
assert(!store.copyVisualChannel(accountId: account, sourcePeerId: source, initial: .init(title: " ")))
assert(!store.setVisualChannelSubscriberCount(accountId: account, sourcePeerId: source, count: -1, initial: initial))
assert(store.setVisualChannelSubscriberCount(accountId: account, sourcePeerId: source, count: 0, initial: initial))
let countOnly = store.visualChannel(accountId: account, sourcePeerId: source)!
assert(!countOnly.isCopied && countOnly.subscriberCountOverride == 0 && countOnly.properties.username == "Actual")
assert(!store.addVisualChannelPost(accountId: account, sourcePeerId: source, text: "no privileges", now: 12))
assert(!store.updateVisualChannelProperties(accountId: account, sourcePeerId: source, properties: initial))

assert(store.copyVisualChannel(accountId: account, sourcePeerId: source, initial: initial))
assert(store.copyVisualChannel(accountId: account, sourcePeerId: additional, initial: initial))
assert(store.visualChannel(accountId: account, sourcePeerId: source)?.subscriberCountOverride == 0)
assert(store.visualChannel(accountId: account, sourcePeerId: additional)?.subscriberCountOverride == nil)
assert(store.visualChannel(accountId: account, sourcePeerId: additional)?.properties.subscriberCount == 420)
assert(store.visualChannels(accountId: other).isEmpty)
assert(!store.addVisualChannelPost(accountId: other, sourcePeerId: source, text: "different account", now: 15))
assert(!store.addVisualChannelPost(accountId: account, sourcePeerId: source, text: " \n ", now: 15))
assert(!store.addVisualChannelPost(accountId: account, sourcePeerId: source, text: String(repeating: "🦆", count: 2049), now: 15))
assert(store.addVisualChannelPost(accountId: account, sourcePeerId: source, text: "First\npost", now: 15))
assert(store.addVisualChannelPost(accountId: account, sourcePeerId: source, text: "Second", now: 15))
let first = store.visualChannel(accountId: account, sourcePeerId: source)!.posts[0]
let second = store.visualChannel(accountId: account, sourcePeerId: source)!.posts[1]
assert(first.id != second.id && first.date == second.date)
assert(store.editVisualChannelPost(accountId: account, sourcePeerId: source, postId: first.id, text: "Edited"))
assert(!store.removeVisualChannelPost(accountId: account, sourcePeerId: additional, postId: first.id))
assert(!store.editVisualChannelPost(accountId: account, sourcePeerId: source, postId: first.id, text: ""))
assert(store.removeVisualChannelPost(accountId: account, sourcePeerId: source, postId: second.id))
let edited = store.visualChannel(accountId: account, sourcePeerId: source)!.posts
assert(edited.count == 1 && edited[0].id == first.id && edited[0].text == "Edited" && edited[0].date == 15)

assert(store.updateVisualChannelProperties(accountId: account, sourcePeerId: source) {
    $0.title = "Edited title"
    $0.about = "Edited description"
    $0.verified = true
    $0.signaturesEnabled = true
    $0.showAuthors = true
    $0.color = 3
})
assert(store.visualChannel(accountId: account, sourcePeerId: source)?.subscriberCountOverride == 0)
assert(!store.updateVisualChannelProperties(accountId: account, sourcePeerId: source) { $0.username = "invalid-link/" })
assert(store.updateVisualChannelProperties(accountId: account, sourcePeerId: source) { $0.subscriberCount = 900 })
assert(store.visualChannel(accountId: account, sourcePeerId: source)?.subscriberCountOverride == 900)
assert(store.updateVisualChannelProperties(accountId: account, sourcePeerId: source) { $0.signaturesEnabled = false })
let customized = store.visualChannel(accountId: account, sourcePeerId: source)!
assert(!customized.properties.showAuthors && customized.properties.verified && customized.properties.color == 3)
assert(store.copyVisualChannel(accountId: account, sourcePeerId: source, initial: .init(title: "New source title")))
assert(store.visualChannel(accountId: account, sourcePeerId: source) == customized)

store.allowWrites = false
assert(!store.addVisualChannelPost(accountId: account, sourcePeerId: source, text: "Uncommitted", now: 18))
assert(!store.removeVisualChannelCopy(accountId: account, sourcePeerId: source))
assert(store.visualChannel(accountId: account, sourcePeerId: source) == customized)
store.allowWrites = true
store.vaultKey = nil
assert(!store.editVisualChannelPost(accountId: account, sourcePeerId: source, postId: first.id, text: "No key"))
store.vaultKey = Data()
VisualGramActivation.shared.allowed = false
assert(store.visualChannels(accountId: account).isEmpty)
assert(store.visualChannel(accountId: account, sourcePeerId: source) == nil)
assert(!store.addVisualChannelPost(accountId: account, sourcePeerId: source, text: "No access", now: 19))
VisualGramActivation.shared.allowed = true
assert(store.visualChannel(accountId: account, sourcePeerId: source) == customized)

let restored = VisualGramLocalAppearance(try JSONDecoder().decode([String: VisualGramAppearance].self, from: store.persisted!))
assert(restored.visualChannel(accountId: account, sourcePeerId: source) == customized)
restored.reset(accountId: account)
assert(!restored.appearance(accountId: account).enabled)
assert(restored.visualChannel(accountId: account, sourcePeerId: source) == customized)
assert(restored.removeVisualChannelCopy(accountId: account, sourcePeerId: source))
let afterDeletion = restored.visualChannel(accountId: account, sourcePeerId: source)!
assert(!afterDeletion.isCopied && afterDeletion.posts.isEmpty && afterDeletion.subscriberCountOverride == 900)
assert(afterDeletion.properties.title == "Original" && !afterDeletion.properties.verified)
assert(restored.setVisualChannelSubscriberCount(accountId: account, sourcePeerId: source, count: nil, initial: initial))
assert(restored.visualChannel(accountId: account, sourcePeerId: source) == nil)
assert(restored.setVisualChannelSubscriberCount(accountId: account, sourcePeerId: additional, count: 999, initial: initial))
var latest = initial
latest.subscriberCount = 485
assert(restored.setVisualChannelSubscriberCount(accountId: account, sourcePeerId: additional, count: nil, initial: latest))
assert(restored.visualChannel(accountId: account, sourcePeerId: additional)?.subscriberCountOverride == nil)
assert(restored.visualChannel(accountId: account, sourcePeerId: additional)?.properties.subscriberCount == 485)

DispatchQueue.concurrentPerform(iterations: 24) { index in
    assert(restored.addVisualChannelPost(accountId: account, sourcePeerId: additional, text: "Post \(index)", now: 30))
}
let concurrent = restored.visualChannel(accountId: account, sourcePeerId: additional)!.posts
assert(concurrent.count == 24 && Set(concurrent.map(\.id)).count == 24)
assert(restored.removeVisualChannelCopy(accountId: account, sourcePeerId: additional))
assert(restored.visualChannels(accountId: account).isEmpty)
print("PASS: visual channel copies, count overrides, persistence, post editing, and access gates")
'''


def main():
    with tempfile.TemporaryDirectory() as root:
        swift = Path(root) / "VisualChannelTests.swift"
        binary = Path(root) / "VisualChannelTests"
        swift.write_text(source(), encoding="utf-8")
        subprocess.run(["xcrun", "swiftc", str(swift), "-o", str(binary)], check=True)
        subprocess.run([str(binary)], check=True)


if __name__ == "__main__":
    main()
