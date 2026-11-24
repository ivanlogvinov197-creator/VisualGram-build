"""Exercise the on-device account store with the real Swift implementation."""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def source():
    store = (ROOT / "native/DuckGramLocalAccountStore.swift").read_text(encoding="utf-8")
    return store + r'''

let first = "+88810000001"
let second = "+88810000002"
let third = "+88810000003"
let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
defer { try? FileManager.default.removeItem(at: directory) }
let file = directory.appendingPathComponent("local/workspace.json")
let store = DuckGramLocalAccountStore(fileURL: file)

assert(DuckGramLocalAccountStore.localNumber("+888 (1000) 0001") == first)
for invalid in ["+79991234567", "+888", "88810000001", "+888other", "++88810000001"] {
    assert(DuckGramLocalAccountStore.localNumber(invalid) == nil)
}
let initial = try store.snapshot()
assert(initial.profiles.isEmpty && initial.activeNumber == nil)
for invalidCode in ["", " \n", "1234", "123456", "12a45", "123４5", "١٢٣٤٥"] {
    do {
        _ = try store.signIn(number: first, code: invalidCode)
        fatalError("Only a five-digit code may select a profile")
    } catch DuckGramLocalAccountStore.InputError.invalidCode {}
}
do {
    _ = try store.signIn(number: "+79991234567", code: "12345")
    fatalError("A Telegram-only number must not create a local profile")
} catch DuckGramLocalAccountStore.InputError.invalidNumber {}

let a = try store.signIn(number: first, code: "57246")
assert(a.profiles == [first] && a.activeNumber == first)
do {
    _ = try store.send(text: "hello", from: first, to: second)
    fatalError("An unknown recipient must not receive a message")
} catch DuckGramLocalAccountStore.InputError.invalidRecipient {}
let b = try store.signIn(number: second, code: "00000")
assert(b.profiles == [first, second] && b.activeNumber == second)
do {
    _ = try store.send(text: "stale sender", from: first, to: second)
    fatalError("A previously selected profile must not send")
} catch DuckGramLocalAccountStore.InputError.invalidRecipient {}
do {
    _ = try store.send(text: " \n ", from: second, to: first)
    fatalError("Blank messages must not be saved")
} catch DuckGramLocalAccountStore.InputError.emptyMessage {}
let sent = try store.send(text: " from B ", from: second, to: first)
assert(sent.messages(between: first, and: second).map(\.text) == ["from B"])
assert(sent.messages(between: first, and: third).isEmpty)

let again = try store.signIn(number: "+888 1000 0001", code: "00123")
assert(again.profiles == [first, second] && again.activeNumber == first)
assert(again.messages(between: first, and: second).map(\.sender) == [second])
let replied = try store.send(text: "from A", from: first, to: second)
assert(replied.messages(between: second, and: first).map(\.text) == ["from B", "from A"])

let reopened = DuckGramLocalAccountStore(fileURL: file)
let restored = try reopened.snapshot()
assert(restored.activeNumber == first && restored.profiles == [first, second])
assert(restored.messages(between: second, and: first).map(\.id) ==
       replied.messages(between: first, and: second).map(\.id))
try reopened.signOut()
let signedOut = try DuckGramLocalAccountStore(fileURL: file).snapshot()
assert(signedOut.activeNumber == nil && signedOut.profiles == [first, second])
assert(signedOut.messages(between: first, and: second).count == 2)
let raw = try String(contentsOf: file, encoding: .utf8)
let storedFields = try JSONSerialization.jsonObject(with: Data(raw.utf8)) as! [String: Any]
assert(Set(storedFields.keys) == Set(["profiles", "threads"]))

let blockedDirectory = directory.appendingPathComponent("blocked")
let unwritable = DuckGramLocalAccountStore(fileURL: blockedDirectory.appendingPathComponent("file"))
let beforeFailure = try unwritable.snapshot()
assert(beforeFailure.profiles.isEmpty)
try Data().write(to: blockedDirectory)
do {
    _ = try unwritable.signIn(number: first, code: "43210")
    fatalError("A failed write must not report successful login")
} catch {}
let afterFailure = try unwritable.snapshot()
assert(afterFailure.profiles.isEmpty && afterFailure.activeNumber == nil)

let corruptFile = directory.appendingPathComponent("corrupt")
let corruptData = Data("damaged".utf8)
try corruptData.write(to: corruptFile)
let corrupt = DuckGramLocalAccountStore(fileURL: corruptFile)
do {
    _ = try corrupt.signIn(number: first, code: "43210")
    fatalError("Unreadable history must not be overwritten")
} catch {}
let preserved = try Data(contentsOf: corruptFile)
assert(preserved == corruptData)
print("PASS: local profiles, five-digit codes, message isolation and persistence")
'''


def main():
    with tempfile.TemporaryDirectory() as temporary:
        path = Path(temporary)
        swift = path / "LocalAccountsTests.swift"
        program = path / "local-accounts-tests"
        swift.write_text(source(), encoding="utf-8")
        subprocess.run(["xcrun", "swiftc", str(swift), "-o", str(program)], check=True)
        subprocess.run([str(program)], check=True)


if __name__ == "__main__":
    main()
