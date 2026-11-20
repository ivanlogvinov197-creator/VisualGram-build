import Foundation
import CryptoKit
import Security

struct VisualGramSignedAccess {
    private let payload: Data
    private let signature: Data
    private let publicKey: Data
    private let device: String
    private let request: String
    private let startUptime: TimeInterval

    init?(payload: Data, signature: Data, publicKey: Data, device: String, request: String, startUptime: TimeInterval) {
        guard startUptime.isFinite, startUptime >= 0,
              VisualGramActivationGrant.verify(payload: payload, signature: signature, publicKey: publicKey, device: device, request: request) != nil else { return nil }
        self.payload = payload
        self.signature = signature
        self.publicKey = publicKey
        self.device = device
        self.request = request
        self.startUptime = startUptime
    }

    func permitsAccess(uptime: TimeInterval) -> Bool {
        guard let grant = VisualGramActivationGrant.verify(payload: self.payload, signature: self.signature, publicKey: self.publicKey, device: self.device, request: self.request) else { return false }
        return grant.permitsAccess(startUptime: self.startUptime, uptime: uptime)
    }

    func storageKey(id: String, uptime: TimeInterval) -> Data? {
        guard let grant = VisualGramActivationGrant.verify(payload: self.payload, signature: self.signature, publicKey: self.publicKey, device: self.device, request: self.request),
              grant.permitsAccess(startUptime: self.startUptime, uptime: uptime),
              grant.storage_id == id, let encoded = grant.storage_key,
              let key = Data(base64Encoded: encoded), key.count == 32 else { return nil }
        return key
    }
}

enum VisualGramAppearanceCipher {
    static let storageName = "visualgram.appearance.v4"
    static let identityName = "visualgram.appearance.vault.v1"

    static func identity(defaults: UserDefaults) -> String {
        if let id = defaults.string(forKey: identityName), validIdentity(id) { return id }
#if os(iOS)
        // Keep the public vault identifier with the device key across ordinary reinstalls.
        let query: [String: Any] = [kSecClass as String: kSecClassGenericPassword,
                                   kSecAttrService as String: "app.visualgram.appearance.v1",
                                   kSecAttrAccount as String: "vault-id"]
        var read = query
        read[kSecReturnData as String] = true
        var item: CFTypeRef?
        if SecItemCopyMatching(read as CFDictionary, &item) == errSecSuccess,
           let data = item as? Data, let id = String(data: data, encoding: .utf8), validIdentity(id) {
            defaults.set(id, forKey: identityName)
            return id
        }
#endif
        let id = UUID().uuidString.replacingOccurrences(of: "-", with: "").lowercased()
#if os(iOS)
        var insert = query
        insert[kSecValueData as String] = Data(id.utf8)
        insert[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        _ = SecItemAdd(insert as CFDictionary, nil)
#endif
        defaults.set(id, forKey: identityName)
        return id
    }

    static func validIdentity(_ id: String) -> Bool {
        return id.count == 32 && id.allSatisfy { "0123456789abcdef".contains($0) }
    }

    static func seal(_ data: Data, key: Data, id: String) throws -> Data {
        guard key.count == 32, validIdentity(id) else { throw CocoaError(.coderInvalidValue) }
        let sealed = try AES.GCM.seal(data, using: SymmetricKey(data: key), authenticating: Data(("duckgram.appearance.v4:" + id).utf8))
        guard let combined = sealed.combined else { throw CocoaError(.coderInvalidValue) }
        return combined
    }

    static func open(_ data: Data, key: Data, id: String) throws -> Data {
        guard key.count == 32, validIdentity(id) else { throw CocoaError(.coderInvalidValue) }
        return try AES.GCM.open(AES.GCM.SealedBox(combined: data), using: SymmetricKey(data: key), authenticating: Data(("duckgram.appearance.v4:" + id).utf8))
    }

    static func fingerprint(_ value: String) -> String {
        return SHA256.hash(data: Data(value.utf8)).map { String(format: "%02x", $0) }.joined()
    }
}

private final class VisualGramActivationSessionDelegate: NSObject, URLSessionTaskDelegate {
    func urlSession(_ session: URLSession, task: URLSessionTask, willPerformHTTPRedirection response: HTTPURLResponse, newRequest request: URLRequest, completionHandler: @escaping (URLRequest?) -> Void) {
        completionHandler(nil)
    }
}

// The server key is public. Neither code-generation nor signing secrets ship in the IPA.
struct VisualGramActivationGrant: Codable {
    let v: Int
    let device: String
    let request: String
    let server_time: Int64
    let trial_until: Int64
    let status: String
    let lease_seconds: Int
    var storage_id: String? = nil
    var storage_key: String? = nil

    static func verify(payload: Data, signature: Data, publicKey: Data, device: String, request: String) -> VisualGramActivationGrant? {
        guard !payload.isEmpty, payload.count <= 4096, signature.count == 64, publicKey.count == 32,
              let key = try? Curve25519.Signing.PublicKey(rawRepresentation: publicKey),
              key.isValidSignature(signature, for: payload),
              let grant = try? JSONDecoder().decode(Self.self, from: payload),
              grant.v == 1, grant.device == device, grant.request == request,
              grant.server_time > 0, grant.trial_until > 0,
              ["trial", "active", "expired"].contains(grant.status),
              (0...300).contains(grant.lease_seconds) else { return nil }
        if grant.status == "trial" {
            guard grant.server_time < grant.trial_until,
                  Int64(grant.lease_seconds) <= grant.trial_until - grant.server_time else { return nil }
        } else if grant.status == "expired" && grant.lease_seconds != 0 { return nil }
        return grant
    }

    func permitsAccess(startUptime: TimeInterval, uptime: TimeInterval) -> Bool {
        guard status == "trial" || status == "active", lease_seconds > 0,
              uptime.isFinite, startUptime.isFinite, uptime >= startUptime else { return false }
        return uptime - startUptime < Double(lease_seconds)
    }
}

public final class VisualGramActivation {
    public static let shared = VisualGramActivation()
    public static let changed = Notification.Name("VisualGramActivationChanged.v1")
    private static let endpoint = URL(string: "https://pay.duckgram.shop")!
    private static let serverKey = Data(base64Encoded: "ssqxs6TifZnbxIyDvCVLV0YOO3DZ8fyrVgT/Bs0Evj0=")!
    private let lock = NSLock()
    private var grant: VisualGramActivationGrant?
    private var signedAccess: VisualGramSignedAccess?
    private var grantUptime: TimeInterval = 0
    private var message = "Для проверки доступа подключитесь к интернету."
    private var started = false
    private var foreground = false
    private var reportedAccess = false
    private var vendorIdentifier: String?
    private var inFlight = false
    private var generation = 0
    private var timer: Timer?
    private var observers: [NSObjectProtocol] = []
    private var key: SecKey?
    private var hint: String?
    private let session: URLSession
    private let storageId = VisualGramAppearanceCipher.identity(defaults: .standard)

    private init() {
        let config = URLSessionConfiguration.ephemeral
        config.timeoutIntervalForRequest = 12
        config.timeoutIntervalForResource = 20
        config.urlCache = nil
        config.httpCookieStorage = nil
        config.httpShouldSetCookies = false
        self.session = URLSession(configuration: config, delegate: VisualGramActivationSessionDelegate(), delegateQueue: nil)
    }

    public var hasAccess: Bool {
        self.lock.lock(); defer { self.lock.unlock() }
        return self.grant?.permitsAccess(startUptime: self.grantUptime, uptime: ProcessInfo.processInfo.systemUptime) ?? false
    }

    @inline(__always)
    func authorizesAppearance() -> Bool {
        self.lock.lock()
        let access = self.signedAccess
        self.lock.unlock()
        return access?.storageKey(id: self.storageId, uptime: ProcessInfo.processInfo.systemUptime) != nil
    }

    func appearanceStorageKey() -> Data? {
        self.lock.lock()
        let access = self.signedAccess
        self.lock.unlock()
        return access?.storageKey(id: self.storageId, uptime: ProcessInfo.processInfo.systemUptime)
    }

    public var statusText: String {
        self.lock.lock(); defer { self.lock.unlock() }
        guard let grant = self.grant else { return self.message }
        guard grant.permitsAccess(startUptime: self.grantUptime, uptime: ProcessInfo.processInfo.systemUptime) else {
            return grant.status == "expired" ? "Срок доступа истёк. Введите код активации." : "Требуется проверка доступа через интернет."
        }
        if grant.status == "active" { return "Доступ активирован для этого устройства." }
        let elapsed = max(0, ProcessInfo.processInfo.systemUptime - self.grantUptime)
        let remaining = max(0, Double(grant.trial_until - grant.server_time) - elapsed)
        return "Пробный доступ: осталось \(Int(remaining) / 3600) ч \((Int(remaining) % 3600) / 60) мин."
    }

    public func start(vendorIdentifier: String?, isForeground: Bool, activeNotification: Notification.Name, backgroundNotification: Notification.Name) {
        if !Thread.isMainThread { DispatchQueue.main.async { self.start(vendorIdentifier:vendorIdentifier,isForeground:isForeground,activeNotification:activeNotification,backgroundNotification:backgroundNotification) }; return }
        guard !self.started else { return }
        self.started = true
        self.foreground = isForeground
        self.vendorIdentifier = vendorIdentifier
        self.observers.append(NotificationCenter.default.addObserver(forName: backgroundNotification, object: nil, queue: .main) { [weak self] _ in
            self?.foreground = false

        })
        self.observers.append(NotificationCenter.default.addObserver(forName: activeNotification, object: nil, queue: .main) { [weak self] _ in
            self?.foreground = true
            self?.refresh()
        })
        let timer = Timer(timeInterval: 15, repeats: true) { [weak self] _ in self?.tick() }
        self.timer = timer
        RunLoop.main.add(timer, forMode: .common)
        self.refresh()
    }

    private func notify() {
        let access = self.authorizesAppearance()
        guard access != self.reportedAccess else { return }
        self.reportedAccess = access
        NotificationCenter.default.post(name: Self.changed, object: nil)
    }

    private func invalidate(message: String) {
        self.generation &+= 1
        self.inFlight = false
        self.lock.lock()
        self.grant = nil
        self.signedAccess = nil
        self.message = message
        self.lock.unlock()
        self.notify()
    }

    private func tick() {
        guard self.foreground else { return }
        self.lock.lock()
        let age = ProcessInfo.processInfo.systemUptime - self.grantUptime
        let hasGrant = self.grant != nil
        self.lock.unlock()
        self.notify()
        if !self.inFlight && (!hasGrant || !self.hasAccess || age >= 120) { self.refresh() }
    }

    private func identity() throws -> (SecKey, Data, String) {
        let tag = Data("app.visualgram.activation.secureenclave.v1".utf8)
        if self.key == nil {
            let query: [String: Any] = [kSecClass as String:kSecClassKey, kSecAttrApplicationTag as String:tag, kSecAttrKeyType as String:kSecAttrKeyTypeECSECPrimeRandom, kSecReturnRef as String:true]
            var found: CFTypeRef?
            let result = SecItemCopyMatching(query as CFDictionary, &found)
            if result == errSecSuccess, let found = found { self.key = (found as! SecKey) }
            else if result == errSecItemNotFound {
                guard let access = SecAccessControlCreateWithFlags(nil, kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly, [.privateKeyUsage], nil) else { throw self.failure() }
                let attributes: [String: Any] = [kSecAttrKeyType as String:kSecAttrKeyTypeECSECPrimeRandom, kSecAttrKeySizeInBits as String:256, kSecAttrTokenID as String:kSecAttrTokenIDSecureEnclave, kSecPrivateKeyAttrs as String:[kSecAttrIsPermanent as String:true, kSecAttrApplicationTag as String:tag, kSecAttrAccessControl as String:access]]
                self.key = SecKeyCreateRandomKey(attributes as CFDictionary, nil)
            } else { throw self.failure() }
        }
        guard let key = self.key, let publicKey = SecKeyCopyPublicKey(key),
              let raw = SecKeyCopyExternalRepresentation(publicKey, nil) as Data?, raw.count == 65 else { throw self.failure() }
        if self.hint == nil {
            let query: [String:Any] = [kSecClass as String:kSecClassGenericPassword, kSecAttrService as String:"app.visualgram.activation.v1", kSecAttrAccount as String:"device-hint", kSecReturnData as String:true]
            var item: CFTypeRef?
            let result = SecItemCopyMatching(query as CFDictionary, &item)
            if result == errSecSuccess, let data = item as? Data, let text = String(data:data,encoding:.utf8), text.count == 64 {
                self.hint = text
            } else if result == errSecItemNotFound {
                let source = self.vendorIdentifier ?? UUID().uuidString
                let text = self.hex(Data(SHA256.hash(data:Data(("visualgram-v1:" + source).utf8))))
                var insert = query
                insert.removeValue(forKey:kSecReturnData as String)
                insert[kSecValueData as String] = Data(text.utf8)
                insert[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
                guard SecItemAdd(insert as CFDictionary, nil) == errSecSuccess else { throw self.failure() }
                self.hint = text
            } else { throw self.failure() }
        }
        guard let hint = self.hint else { throw self.failure() }
        return (key, raw, hint)
    }

    private func hex(_ data: Data) -> String { return data.map { String(format:"%02x",$0) }.joined() }
    private func failure() -> NSError { return NSError(domain:"VisualGramActivation",code:1,userInfo:[NSLocalizedDescriptionKey:"Не удалось проверить доступ. Проверьте подключение и повторите."]) }

    private func post(_ path: String, _ body: [String:Any], completion: @escaping (Result<[String:Any],Error>) -> Void) {
        var request = URLRequest(url:Self.endpoint.appendingPathComponent(path))
        request.httpMethod = "POST"
        request.setValue("application/json",forHTTPHeaderField:"Content-Type")
        request.cachePolicy = .reloadIgnoringLocalAndRemoteCacheData
        request.httpBody = try? JSONSerialization.data(withJSONObject:body)
        self.session.dataTask(with:request) { data,response,error in
            let result: Result<[String:Any],Error>
            if let error = error { result = .failure(error) }
            else if let data = data, data.count <= 4096, let object = (try? JSONSerialization.jsonObject(with:data)) as? [String:Any], let response = response as? HTTPURLResponse {
                if response.statusCode == 200 { result = .success(object) }
                else {
                    let code = object["error"] as? String ?? ""
                    let text: String
                    switch code {
                    case "code_invalid_or_used": text = "Код неверен, отозван или уже привязан к другому устройству."
                    case "device_revoked": text = "Доступ для этого устройства отозван."
                    case "already_activated": text = "Устройство уже активировано другим кодом."
                    case "too_many_requests": text = "Слишком много попыток. Повторите через минуту."
                    default: text = "Не удалось проверить доступ. Повторите позже."
                    }
                    result = .failure(NSError(domain:"VisualGramActivation",code:response.statusCode,userInfo:[NSLocalizedDescriptionKey:text]))
                }
            } else { result = .failure(self.failure()) }
            DispatchQueue.main.async { completion(result) }
        }.resume()
    }

    public func refresh(code: String = "", completion: ((String?) -> Void)? = nil) {
        if !Thread.isMainThread { DispatchQueue.main.async { self.refresh(code:code, completion:completion) }; return }
        guard !self.inFlight else { completion?("Проверка уже выполняется. Подождите несколько секунд."); return }
        guard self.foreground else { completion?("Откройте приложение для проверки доступа."); return }
        let normalized = code.uppercased().replacingOccurrences(of:"-",with:"").replacingOccurrences(of:" ",with:"").trimmingCharacters(in:.whitespacesAndNewlines)
        guard normalized.isEmpty || (normalized.count == 32 && normalized.allSatisfy { "0123456789ABCDEF".contains($0) }) else { completion?("Проверьте формат кода активации."); return }
        let identity: (SecKey,Data,String)
        do { identity = try self.identity() }
        catch { self.invalidate(message:"Не удалось получить защищённый ключ устройства. Разблокируйте iPhone и повторите проверку."); completion?(self.statusText); return }
        self.inFlight = true
        self.generation &+= 1
        let generation = self.generation
        let startUptime = ProcessInfo.processInfo.systemUptime
        let rawKey = identity.1.base64EncodedString()
        let hint = identity.2
        self.post("v1/challenge",["public_key":rawKey,"device_hint":hint]) { [weak self] result in
            guard let self = self, self.generation == generation else { return }
            switch result {
            case let .failure(error): self.finish(error:error, completion:completion)
            case let .success(challenge):
                guard let id = challenge["id"] as? String, id.count == 48, id.allSatisfy({ "0123456789abcdef".contains($0) }),
                      let nonce = challenge["nonce"] as? String, Data(base64Encoded:nonce)?.count == 32 else { self.finish(error:self.failure(),completion:completion); return }
                let codeHash = self.hex(Data(SHA256.hash(data:Data(normalized.utf8))))
                let proof = Data("visualgram-v1\n\(id)\n\(nonce)\n\(hint)\n\(codeHash)\nduckgram-storage-v1\n\(self.storageId)".utf8)
                guard let signature = SecKeyCreateSignature(identity.0,.ecdsaSignatureMessageX962SHA256,proof as CFData,nil) as Data? else { self.finish(error:self.failure(),completion:completion); return }
                self.post("v1/session",["public_key":rawKey,"device_hint":hint,"challenge_id":id,"signature":signature.base64EncodedString(),"code":normalized,"storage_id":self.storageId]) { [weak self] result in
                    guard let self = self, self.generation == generation else { return }
                    switch result {
                    case let .failure(error): self.finish(error:error,completion:completion)
                    case let .success(object):
                        guard let payloadString = object["payload"] as? String, let payload = Data(base64Encoded:payloadString),
                              let signatureString = object["signature"] as? String, let signature = Data(base64Encoded:signatureString),
                              let grant = VisualGramActivationGrant.verify(payload:payload,signature:signature,publicKey:Self.serverKey,device:self.hex(Data(SHA256.hash(data:identity.1))),request:id),
                              let access = VisualGramSignedAccess(payload: payload, signature: signature, publicKey: Self.serverKey, device: grant.device, request: id, startUptime: startUptime) else { self.finish(error:self.failure(),completion:completion); return }
                        if grant.permitsAccess(startUptime: startUptime, uptime: ProcessInfo.processInfo.systemUptime),
                           access.storageKey(id: self.storageId, uptime: ProcessInfo.processInfo.systemUptime) == nil {
                            self.finish(error: self.failure(), completion: completion)
                            return
                        }
                        self.inFlight = false
                        self.lock.lock(); self.grant = grant; self.signedAccess = access; self.grantUptime = startUptime; self.lock.unlock()
                        self.notify()
                        completion?(nil)
                    }
                }
            }
        }
    }

    private func finish(error: Error, completion: ((String?) -> Void)?) {
        let text = (error as NSError).domain == "VisualGramActivation" ? error.localizedDescription : "Сервер недоступен. Подключитесь к интернету и повторите проверку."
        if (error as NSError).domain == "VisualGramActivation" && (error as NSError).code == 403 && text == "Доступ для этого устройства отозван." {
            self.invalidate(message: text)
        } else {
            self.inFlight = false
            self.lock.lock(); self.message = text; self.lock.unlock()
            self.notify()
        }
        completion?(text)
    }
}
