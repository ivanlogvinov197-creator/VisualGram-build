import Foundation

final class DuckGramLocalAccountStore {
    struct Message: Codable, Identifiable {
        let id: UUID
        let sender: String
        let text: String
        let date: Date
    }

    struct Snapshot: Codable {
        fileprivate(set) var profiles: [String] = []
        fileprivate(set) var activeNumber: String?
        fileprivate var threads: [String: [Message]] = [:]

        func messages(between first: String, and second: String) -> [Message] {
            self.threads[DuckGramLocalAccountStore.threadKey(first, second)] ?? []
        }
    }

    enum InputError: Error {
        case invalidNumber
        case invalidCode
        case invalidRecipient
        case emptyMessage
    }

    static let codeLength = 5

    static let shared = DuckGramLocalAccountStore(fileURL:
        FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("DuckGramLocalAccounts", isDirectory: true)
            .appendingPathComponent("workspace-v1.json")
    )

    private let fileURL: URL
    private let lock = NSLock()
    private var cached: Snapshot?

    init(fileURL: URL) {
        self.fileURL = fileURL
    }

    static func localNumber(_ input: String) -> String? {
        let number = String(input.filter { !$0.isWhitespace && !"-()".contains($0) })
        guard number.hasPrefix("+888"), number.count > 4, number.count <= 16,
              number.dropFirst().utf8.allSatisfy({ (48...57).contains($0) }) else { return nil }
        return number
    }

    static func isValidCode(_ code: String) -> Bool {
        code.utf8.count == Self.codeLength && code.utf8.allSatisfy { (48...57).contains($0) }
    }

    func snapshot() throws -> Snapshot {
        self.lock.lock()
        defer { self.lock.unlock() }
        return try self.load()
    }

    func signIn(number input: String, code: String) throws -> Snapshot {
        guard let number = Self.localNumber(input) else { throw InputError.invalidNumber }
        guard Self.isValidCode(code) else { throw InputError.invalidCode }
        return try self.update { snapshot in
            if !snapshot.profiles.contains(number) {
                snapshot.profiles.append(number)
            }
            snapshot.activeNumber = number
        }
    }

    func signOut() throws {
        _ = try self.update { $0.activeNumber = nil }
    }

    func send(text input: String, from sender: String, to recipient: String) throws -> Snapshot {
        let text = input.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { throw InputError.emptyMessage }
        return try self.update { snapshot in
            guard snapshot.activeNumber == sender, sender != recipient,
                  snapshot.profiles.contains(sender), snapshot.profiles.contains(recipient) else {
                throw InputError.invalidRecipient
            }
            snapshot.threads[Self.threadKey(sender, recipient), default: []].append(
                Message(id: UUID(), sender: sender, text: text, date: Date())
            )
        }
    }

    private static func threadKey(_ first: String, _ second: String) -> String {
        [first, second].sorted().joined(separator: "|")
    }

    private func load() throws -> Snapshot {
        if let cached = self.cached {
            return cached
        }
        let snapshot: Snapshot
        do {
            snapshot = try JSONDecoder().decode(Snapshot.self, from: Data(contentsOf: self.fileURL))
        } catch let error as NSError where Self.isMissingFile(error) {
            snapshot = Snapshot()
        }
        self.cached = snapshot
        return snapshot
    }

    private static func isMissingFile(_ error: NSError) -> Bool {
        if error.domain == NSCocoaErrorDomain {
            return error.code == NSFileReadNoSuchFileError || error.code == NSFileNoSuchFileError
        }
        return error.domain == NSPOSIXErrorDomain && error.code == Int(POSIXErrorCode.ENOENT.rawValue)
    }

    private func update(_ change: (inout Snapshot) throws -> Void) throws -> Snapshot {
        self.lock.lock()
        defer { self.lock.unlock() }
        var snapshot = try self.load()
        try change(&snapshot)
        let directory = self.fileURL.deletingLastPathComponent()
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let data = try JSONEncoder().encode(snapshot)
#if os(iOS)
        var privateDirectory = directory
        var resourceValues = URLResourceValues()
        resourceValues.isExcludedFromBackup = true
        try privateDirectory.setResourceValues(resourceValues)
        try data.write(to: self.fileURL, options: [.atomic, .completeFileProtection])
#else
        try data.write(to: self.fileURL, options: .atomic)
#endif
        self.cached = snapshot
        return snapshot
    }
}
