"""Execute real signed-lease policy and real central appearance guards on macOS."""
from pathlib import Path
import subprocess
import tempfile
import test_native_delivery as delivery

ROOT = Path(__file__).resolve().parents[1]

def policy_source():
    native = (ROOT/'native/VisualGramActivation.swift').read_text(encoding='utf-8')
    policy = native[:native.index('public final class VisualGramActivation')]
    policy = policy.replace('import Security\n','').replace('import UIKit\n','')
    return policy + r'''
let key = Curve25519.Signing.PrivateKey()
let publicKey = key.publicKey.rawRepresentation
func envelope(_ status: String = "trial", lease: Int = 300, time: Int64 = 1000, until: Int64 = 2000, licenseUntil: Int64? = nil) -> (Data,Data) {
    var fields: [String: Any] = ["v":1,"device":"device","request":"request","server_time":time,"trial_until":until,"status":status,"lease_seconds":lease]
    if let licenseUntil { fields["license_until"] = licenseUntil }
    let payload = try! JSONSerialization.data(withJSONObject: fields)
    return (payload,try! key.signature(for:payload))
}
func verify(_ data: (Data,Data), device: String = "device", request: String = "request") -> VisualGramActivationGrant? {
    VisualGramActivationGrant.verify(payload:data.0,signature:data.1,publicKey:publicKey,device:device,request:request)
}
let valid = envelope()
let grant = verify(valid)!
let access = VisualGramSignedAccess(payload:valid.0,signature:valid.1,publicKey:publicKey,device:"device",request:"request",startUptime:100)!
assert(access.permitsAccess(uptime:399.999))
assert(!access.permitsAccess(uptime:400))
assert(!access.permitsAccess(uptime:99))
assert(!access.permitsAccess(uptime:.infinity))
assert(VisualGramSignedAccess(payload:envelope("active").0,signature:valid.1,publicKey:publicKey,device:"device",request:"request",startUptime:100)==nil)
assert(VisualGramSignedAccess(payload:valid.0,signature:valid.1,publicKey:publicKey,device:"other",request:"request",startUptime:100)==nil)
assert(VisualGramSignedAccess(payload:valid.0,signature:valid.1,publicKey:publicKey,device:"device",request:"replay",startUptime:100)==nil)
assert(VisualGramSignedAccess(payload:valid.0,signature:valid.1,publicKey:publicKey,device:"device",request:"request",startUptime:.nan)==nil)
assert(grant.permitsAccess(startUptime:100,uptime:100))
assert(grant.permitsAccess(startUptime:100,uptime:399.999))
assert(!grant.permitsAccess(startUptime:100,uptime:400))
assert(!grant.permitsAccess(startUptime:100,uptime:1), "uptime rollback/reboot")
assert(!grant.permitsAccess(startUptime:100,uptime:.infinity))
assert(verify(valid,device:"other")==nil, "device binding")
assert(verify(valid,request:"replay")==nil, "request binding")
assert(verify((envelope("active").0,valid.1))==nil, "tampered signed payload")
assert(verify(envelope(lease:301))==nil)
assert(verify(envelope(lease:-1))==nil)
assert(verify(envelope(time:2001,until:2000))==nil)
assert(verify(envelope(lease:300,time:1999,until:2000))==nil)
assert(verify(envelope("expired",lease:1))==nil)
assert(verify(envelope("unknown"))==nil)
assert(!verify(envelope("expired",lease:0))!.permitsAccess(startUptime:100,uptime:100))
assert(verify(envelope("active",time:999999,until:1))!.permitsAccess(startUptime:100,uptime:200))
assert(grant.statusText(startUptime:100,uptime:100) == "Пробный доступ\nОсталось 16 мин")
let permanent = verify(envelope("active"))!
assert(permanent.statusText(startUptime:100,uptime:100) == "Доступ активен.")
let temporary = verify(envelope("active", until:1, licenseUntil:1000 + 187800))!
assert(temporary.statusText(startUptime:100,uptime:100) == "Временный доступ\nОсталось 2 д 4 ч 10 мин")
assert(temporary.statusText(startUptime:100,uptime:160) == "Временный доступ\nОсталось 2 д 4 ч 9 мин")
assert(temporary.statusText(startUptime:100,uptime:400) == "Нужна проверка доступа.")
assert(temporary.statusText(startUptime:100,uptime:99) == "Нужна проверка доступа.")
let almostExpired = verify(envelope("active", lease:59, licenseUntil:1059))!
assert(almostExpired.statusText(startUptime:100,uptime:158) == "Временный доступ\nОсталось меньше минуты")
assert(almostExpired.statusText(startUptime:100,uptime:159) == "Срок доступа истёк.")
assert(verify(envelope("active", licenseUntil:1000)) == nil)
assert(verify(envelope("active", licenseUntil:1299)) == nil)
assert(verify(envelope(licenseUntil:2000)) == nil)
assert(verify(envelope("expired", lease:0, licenseUntil:2000)) == nil)
assert(VisualGramActivationGrant.verify(payload:valid.0,signature:valid.1,publicKey:Curve25519.Signing.PrivateKey().publicKey.rawRepresentation,device:"device",request:"request")==nil)
let vaultId = String(repeating: "a", count: 32)
let vaultKey = Data(repeating: 7, count: 32)
let plaintext = Data("saved visual profile".utf8)
let encrypted = try! VisualGramAppearanceCipher.seal(plaintext, key: vaultKey, id: vaultId)
assert(encrypted != plaintext)
assert((try? VisualGramAppearanceCipher.open(encrypted,key:vaultKey,id:vaultId)) == plaintext)
assert((try? VisualGramAppearanceCipher.open(encrypted,key:Data(repeating:8,count:32),id:vaultId)) == nil)
assert((try? VisualGramAppearanceCipher.open(encrypted,key:vaultKey,id:String(repeating:"b",count:32))) == nil)
var changed = encrypted
changed[changed.startIndex] ^= 1
assert((try? VisualGramAppearanceCipher.open(changed,key:vaultKey,id:vaultId)) == nil)
var fields = try! JSONSerialization.jsonObject(with: valid.0) as! [String:Any]
fields["storage_id"] = vaultId
fields["storage_key"] = vaultKey.base64EncodedString()
let vaultPayload = try! JSONSerialization.data(withJSONObject:fields)
let vaultSignature = try! key.signature(for:vaultPayload)
let vaultAccess = VisualGramSignedAccess(payload:vaultPayload,signature:vaultSignature,publicKey:publicKey,device:"device",request:"request",startUptime:100)!
assert(vaultAccess.storageKey(id:vaultId,uptime:399) == vaultKey)
assert(vaultAccess.storageKey(id:vaultId,uptime:400) == nil)
assert(vaultAccess.storageKey(id:String(repeating:"b",count:32),uptime:100) == nil)
assert(access.storageKey(id:vaultId,uptime:100) == nil)
let benchmarkStart = ProcessInfo.processInfo.systemUptime
for _ in 0..<2000 { assert(vaultAccess.storageKey(id:vaultId,uptime:101)==vaultKey) }
print("METRIC: 2000 signed storage checks in \((ProcessInfo.processInfo.systemUptime-benchmarkStart)*1000) ms")
print("PASS: signed grant, device/request binding, expiry, monotonic clock, invalid/tampered replies")
'''

def store_source():
    source = delivery.source().split(delivery.CHECKS)[0]
    actual = (ROOT/'native/VisualGramLocalAppearance.swift').read_text(encoding='utf-8')
    update = actual[actual.index('    @discardableResult\n    func updateValues('):actual.index('    public func reset(')]
    snapshot = actual[actual.index('    private var vaultKey:'):actual.index('    private init()')]
    cipher = (ROOT/'native/VisualGramActivation.swift').read_text(encoding='utf-8')
    cipher = cipher[cipher.index('enum VisualGramAppearanceCipher'):cipher.index('private final class VisualGramActivationSessionDelegate')]
    source = 'import CryptoKit\n' + cipher + source
    source = source.replace('    private var vaultKey: Data? = Data(repeating: 7, count: 32)\n', '')
    purchase_safety = actual[actual.index('    public func blocksExpiredPurchase('):actual.index('    public var pendingScheduledGifts:')]
    stub = '''    @discardableResult
    func updateValues(recordOperations: Bool = true, allowWhileLocked: Bool = false, _ change: (inout [String: VisualGramAppearance]) -> Void) -> Bool {
        guard VisualGramActivation.shared.hasAccess else { return false }
        change(&values)
        return true
    }'''
    source = source.replace(stub, '''    private var revisionValue: Int32 = 0
    private let revision = ActivationTestPromise()
    static func recordGiftOperations(previous: [String: VisualGramAppearance], values: inout [String: VisualGramAppearance]) {}
''' + update + snapshot + purchase_safety)
    source += r'''
final class ActivationTestPromise { func set(_ value: Int32) {} }
enum Queue { struct Main { func async(_ f: () -> Void) { f() } }; static func mainQueue() -> Main { Main() } }
let store = VisualGramLocalAppearance()
let own = EnginePeer.Id(10)
let gift = VisualGramGift(gift:.generic(.init(id:42,title:"Bear",availability:nil,releasedBy:nil)),counterpartyId:20,direction:.sent,date:1,text:"caption")
var legacyProfile = VisualGramAppearance()
legacyProfile.enabled=true; legacyProfile.gifts=[gift]; legacyProfile.stars=321
store.values["10"] = legacyProfile
store.seedLegacyForTesting()
let legacyValues = store.values
VisualGramActivation.shared.hasAccess=false
store.restoreProtectedValuesForTesting()
assert(store.protectedBytesForTesting() == nil && store.legacyDataForTesting() != nil)
assert(store.values==legacyValues, "legacy values lost before server grants key")
VisualGramActivation.shared.hasAccess=true
store.restoreProtectedValuesForTesting()
assert(store.values==legacyValues && store.legacyDataForTesting()==nil, "legacy migration lost values")
assert(store.protectedBytesForTesting() != nil)
store.update(accountId:own) { $0.enabled=true; $0.premium=true; $0.stars=500; $0.grams=100; $0.gifts=[gift] }
store.scheduleGift(accountId:own,targetPeerId:own,gift:gift,deliveryDate:10)
let saved = store.values
let plaintextBeforeLock = store.encodedValuesForTesting()!
assert(store.protectedBytesForTesting()! != plaintextBeforeLock)
assert(store.legacyDataForTesting() == nil)
VisualGramActivation.shared.hasAccess=false
assert(store.appearance(accountId:own)==VisualGramAppearance(), "locked appearance leaked")
assert(store.snapshotValues().isEmpty, "market data leaked")
assert(store.pendingScheduledGifts.isEmpty)
assert(store.deliverAllScheduledGifts(now:100).isEmpty)
var changed=false
store.update(accountId:own) { _ in changed=true }
assert(!changed && store.values==saved,"locked mutation or data loss")
assert(store.blocksExpiredPurchase(accountId:own),"expired local purchase falls through")
VisualGramActivation.shared.hasAccess=true
VisualGramActivation.shared.appearanceAuthorization=false
assert(store.appearance(accountId:own)==VisualGramAppearance(), "forcing UI access exposed stored appearance")
assert(store.snapshotValues().isEmpty)
var tampered=false
store.update(accountId:own) { _ in tampered=true }
assert(!tampered && store.values==saved, "forcing UI access enabled changes")
assert(store.blocksExpiredPurchase(accountId:own))
VisualGramActivation.shared.appearanceAuthorization=nil
assert(store.appearance(accountId:own).gifts.count==1)
assert(store.appearance(accountId:own).stars==500)
assert(!store.pendingScheduledGifts.isEmpty,"activation did not restore schedules")
assert(!store.blocksExpiredPurchase(accountId:own))
store.restoreProtectedValuesForTesting()
assert(store.values==saved)
let encryptedBeforeDamage = store.protectedBytesForTesting()!
store.damageStorageForTesting()
store.restoreProtectedValuesForTesting()
assert(store.values.isEmpty)
assert(store.blocksExpiredPurchase(accountId:own), "corrupt encrypted state fell through to real payment")
var wroteAfterDamage=false
store.update(accountId:own) { _ in wroteAfterDamage=true }
assert(!wroteAfterDamage)
store.replaceProtectedBytesForTesting(encryptedBeforeDamage)
store.restoreProtectedValuesForTesting()
assert(store.values==saved)
// Cold launch has no decrypted values. Chat deletion while locked must survive unlock.
VisualGramActivation.shared.hasAccess=false
store.restoreProtectedValuesForTesting()
assert(store.values.isEmpty)
assert(store.blocksExpiredPurchase(accountId:own), "cold locked store lost safety index")
store.hideChatGifts(accountId:own,peerId:EnginePeer.Id(20),forEveryone:false)
VisualGramActivation.shared.hasAccess=true
store.restoreProtectedValuesForTesting()
assert(store.appearance(accountId:own).gifts==saved["10"]!.gifts)
assert(!store.hiddenChatGiftKeys(accountId:own,peerId:EnginePeer.Id(20)).isEmpty)
assert(store.hiddenChatGiftKeys(accountId:EnginePeer.Id(20),peerId:own).isEmpty, "delete for self hid receiver copy")
store.hideChatGifts(accountId:own,peerId:EnginePeer.Id(20),forEveryone:true)
assert(!store.hiddenChatGiftKeys(accountId:EnginePeer.Id(20),peerId:own).isEmpty)
let hiddenValues=store.values
store.restoreProtectedValuesForTesting()
assert(store.values==hiddenValues, "deferred deletion not persisted")
print("PASS: real central read/write/schedule/market guards; preserved data restored after activation")
'''
    source = source.replace('    private func restoreProtectedValues()', '    func restoreProtectedValuesForTesting()')
    source = source.replace('    func snapshotValues()', '''
    func encodedValuesForTesting() -> Data? { try? JSONEncoder().encode(self.values) }
    func protectedBytesForTesting() -> Data? { self.defaults.data(forKey:VisualGramAppearanceCipher.storageName) }
    func legacyDataForTesting() -> Data? { self.defaults.data(forKey:"visualgram.appearance.v3") }
    func replaceProtectedBytesForTesting(_ data:Data) { self.defaults.set(data,forKey:VisualGramAppearanceCipher.storageName) }
    func damageStorageForTesting() { self.replaceProtectedBytesForTesting(Data("broken".utf8)) }
    func seedLegacyForTesting() { self.defaults.set(self.encodedValuesForTesting()!,forKey:"visualgram.appearance.v3") }
    func snapshotValues()''')
    return source

def main():
    failures=[]
    with tempfile.TemporaryDirectory() as folder:
        for name, source in [('policy',policy_source()),('store',store_source())]:
            path=Path(folder)/(name+'.swift')
            path.write_text(source,encoding='utf-8')
            output=Path(folder)/name
            try:
                subprocess.run(['xcrun','swiftc',str(path),'-o',str(output)],check=True)
                subprocess.run([str(output)],check=True)
            except subprocess.CalledProcessError:
                failures.append(name)
    sdk=subprocess.check_output(['xcrun','--sdk','iphoneos','--show-sdk-path'],text=True).strip()
    result=subprocess.run(['xcrun','swiftc','-typecheck','-application-extension','-swift-version','5','-warnings-as-errors','-target','arm64-apple-ios15.0','-sdk',sdk,str(ROOT/'native/VisualGramActivation.swift')])
    if result.returncode:failures.append('iPhone client typecheck')
    else:print('PASS: complete activation client typechecked against iPhone SDK')
    if failures:raise RuntimeError('Activation checks failed: '+', '.join(failures))

if __name__=='__main__':main()
