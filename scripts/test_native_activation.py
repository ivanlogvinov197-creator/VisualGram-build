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
func envelope(_ status: String = "trial", lease: Int = 300, time: Int64 = 1000, until: Int64 = 2000) -> (Data,Data) {
    let payload = try! JSONSerialization.data(withJSONObject: ["v":1,"device":"device","request":"request","server_time":time,"trial_until":until,"status":status,"lease_seconds":lease])
    return (payload,try! key.signature(for:payload))
}
func verify(_ data: (Data,Data), device: String = "device", request: String = "request") -> VisualGramActivationGrant? {
    VisualGramActivationGrant.verify(payload:data.0,signature:data.1,publicKey:publicKey,device:device,request:request)
}
let valid = envelope()
let grant = verify(valid)!
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
assert(VisualGramActivationGrant.verify(payload:valid.0,signature:valid.1,publicKey:Curve25519.Signing.PrivateKey().publicKey.rawRepresentation,device:"device",request:"request")==nil)
print("PASS: signed grant, device/request binding, expiry, monotonic clock, invalid/tampered replies")
'''

def store_source():
    source = delivery.source().split(delivery.CHECKS)[0]
    actual = (ROOT/'native/VisualGramLocalAppearance.swift').read_text(encoding='utf-8')
    update = actual[actual.index('    func updateValues('):actual.index('    public func reset(')]
    snapshot = actual[actual.index('    func snapshotValues('):actual.index('    private init()')]
    stub = '    func updateValues(_ change: (inout [String: VisualGramAppearance]) -> Void) { change(&values) }'
    source = source.replace(stub, '''    private let defaults = UserDefaults(suiteName: UUID().uuidString)!
    private var revisionValue: Int32 = 0
    private let revision = ActivationTestPromise()
    static func recordGiftOperations(previous: VisualGramAppearance?, value: inout VisualGramAppearance) {}
''' + update + snapshot)
    source += r'''
final class ActivationTestPromise { func set(_ value: Int32) {} }
enum Queue { struct Main { func async(_ f: () -> Void) { f() } }; static func mainQueue() -> Main { Main() } }
let store = VisualGramLocalAppearance()
let own = EnginePeer.Id(10)
let gift = VisualGramGift(gift:.generic(.init(id:42,title:"Bear",availability:nil,releasedBy:nil)),counterpartyId:nil,date:1,text:"caption")
store.update(accountId:own) { $0.enabled=true; $0.premium=true; $0.stars=500; $0.grams=100; $0.gifts=[gift] }
store.scheduleGift(accountId:own,targetPeerId:own,gift:gift,deliveryDate:10)
let saved = store.values
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
assert(store.appearance(accountId:own).gifts.count==1)
assert(store.appearance(accountId:own).stars==500)
assert(!store.pendingScheduledGifts.isEmpty,"activation did not restore schedules")
assert(!store.blocksExpiredPurchase(accountId:own))
print("PASS: real central read/write/schedule/market guards; preserved data restored after activation")
'''
    return source

def main():
    with tempfile.TemporaryDirectory() as folder:
        for name, source in [('policy',policy_source()),('store',store_source())]:
            path=Path(folder)/(name+'.swift')
            path.write_text(source,encoding='utf-8')
            output=Path(folder)/name
            subprocess.run(['xcrun','swiftc',str(path),'-o',str(output)],check=True)
            subprocess.run([str(output)],check=True)
    sdk=subprocess.check_output(['xcrun','--sdk','iphoneos','--show-sdk-path'],text=True).strip()
    subprocess.run(['xcrun','swiftc','-typecheck','-swift-version','5','-warnings-as-errors','-target','arm64-apple-ios15.0','-sdk',sdk,str(ROOT/'native/VisualGramActivation.swift')],check=True)
    print('PASS: complete activation client typechecked against iPhone SDK')

if __name__=='__main__':main()
