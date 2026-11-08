"""Actual central transactions + event journal + rollback with minimal engine fixtures."""
from pathlib import Path
import subprocess
import tempfile
import test_native_november as november

def source():
    root=Path(__file__).resolve().parents[1]
    base=november.source().split(november.CHECKS)[0]
    base=base.replace('public struct VisualGramAppearance: Codable {', 'public struct VisualGramAppearance: Codable {\n    var peerOverrides: [String: VisualGramAppearance]?')
    base=base.replace('public struct PeerEmojiStatus: Codable {','public struct PeerEmojiStatus: Codable, Equatable {').replace('public enum Content: Codable { case starGift','public enum Content: Codable, Equatable { case starGift')
    base=base.replace('    static func editGiftOperationNarrative(_ original: VisualGramGift, profile: Int64, counterparty: Int64?, date: Int32, text: String, values: inout [String: VisualGramAppearance]) {}\n','')
    actual=(root/'native/VisualGramLocalAppearance.swift').read_text(encoding='utf-8')
    update=actual[actual.index('    func updateValues('):actual.index('    public func reset(')]
    old='    func updateValues(recordOperations: Bool = true, _ change: (inout [String: VisualGramAppearance]) -> Void) { let hook = beforeUpdate; beforeUpdate = nil; hook?(); change(&values) }'
    assert old in base
    base=base.replace(old,'''    private let lock = NSLock()
    private let defaults = UserDefaults(suiteName: UUID().uuidString)!
    private var revisionValue: Int32 = 0
    private let revision = OperationTestPromise()
'''+update)
    old='    func update(accountId: EnginePeer.Id, targetPeerId: EnginePeer.Id? = nil, _ change: (inout VisualGramAppearance) -> Void) { let key = String((targetPeerId ?? accountId).toInt64()); var value = values[key] ?? VisualGramAppearance(); change(&value); values[key] = value }'
    actual_update=actual[actual.index('    public func update(accountId:'):actual.index('    func updateValues(')]
    assert old in base;base=base.replace(old,actual_update)
    management=(root/'native/VisualGramGiftManagement.swift').read_text(encoding='utf-8')
    upgrade=management[management.index('    func upgradeLocalGift('):management.index('    static func makeUpgradedGift(')]
    journal=(root/'native/VisualGramGiftOperations.swift').read_text(encoding='utf-8')
    return base+'\npublic extension VisualGramLocalAppearance {\n'+upgrade+'\n}\n'+journal+CHECKS

CHECKS=r'''
final class OperationTestPromise { func set(_ value: Int32) {} }
enum Queue { struct Main { func async(_ f: () -> Void) { f() } }; static func mainQueue() -> Main { Main() } }
let a=EnginePeer.Id(10), b=EnginePeer.Id(20), c=EnginePeer.Id(30)
func nft(_ id: Int64, chance: Int32? = 500, grams: Int64? = nil) -> StarGift.UniqueGift {
    .init(id:id,giftId:42,title:"Cake",number:Int32(id),slug:"Cake-\(id)",owner:.peerId(a),attributes:[.model(1),.pattern(2),.backdrop(3)],availability:.init(issued:1,total:1000),giftAddress:nil,resellAmounts:grams.map { [CurrencyAmount(amount:.init(value:$0,nanos:0),currency:.ton)] },resellForTonOnly:false,releasedBy:nil,valueAmount:nil,valueCurrency:nil,valueUsdAmount:nil,flags:[],themePeerId:nil,peerColor:nil,hostPeerId:nil,minOfferStars:nil,craftChancePermille:chance)
}
func owned(_ store: VisualGramLocalAppearance,_ who: EnginePeer.Id) -> [VisualGramGift] { store.appearance(accountId:who).gifts.filter { $0.direction == .received && $0.isHistoryOnly != true } }
func operations(_ store: VisualGramLocalAppearance,_ who: EnginePeer.Id) -> [VisualGramGift] { VisualGramLocalAppearance.giftOperations(in:store.appearance(accountId:who)) }
func cancel(_ store: VisualGramLocalAppearance,_ who: EnginePeer.Id,_ op: VisualGramGift) -> VisualGramGiftUndoResult { store.cancelGiftOperation(accountId:a,targetPeerId:who,identifier:op.identifier) }
let attrs: [StarGift.UniqueGift.Attribute]=[.model("Craft",99,1,true),.pattern(2),.backdrop(3)]
let probabilities:[[Int32]]=[[90],[80,200],[70,190,460],[60,180,450,1000]]

// Craft -> transfer stays a transfer in both histories; undo child then parent restores exact inputs.
let s=VisualGramLocalAppearance()
let one=VisualGramGift(gift:.unique(nft(1)),counterpartyId:nil,date:1,text:"one")
let two=VisualGramGift(gift:.unique(nft(2)),counterpartyId:nil,date:2,text:"two")
s.values["10"] = .init(enabled:true,gifts:[one,two],stars:100)
s.values["10"]?.giftOrder=[two.identifier,one.identifier]
s.values["10"]?.gramCardGiftIds=[one.identifier];s.values["10"]?.gramCardBackgroundId=one.identifier
s.values["10"]?.gramCardPlacements=[one.identifier:.init(x:20,y:30)]
s.values["10"]?.overridesEmojiStatus=true;s.values["10"]?.emojiStatus = .init(content:.starGift(1,1,"Cake","Cake-1",1,0,0,0,0))
if case .success = s.craftLocalGifts(accountId:a,references:[one.reference(accountId:a),two.reference(accountId:a)],attributes:attrs,attributePermilles:probabilities,now:100,random:{$0.lowerBound}) {} else { assertionFailure("craft failed") }
let craft=operations(s,a).first { $0.operationEventId != nil && $0.operationKind == .craft }!
assert(craft.operationInputs?.count==2 && craft.operationSucceeded==true && craft.operationResult != nil)
let crafted=owned(s,a).first!
assert(s.transferLocalGift(accountId:a,reference:crafted.reference(accountId:a),recipientPeerId:b,now:200))
let send=operations(s,a).first { $0.operationKind == .transfer }!
assert(send.operationSenderId==10 && send.operationRecipientId==20)
assert(operations(s,b).contains { $0.operationEventId==send.operationEventId && $0.direction == .received })
if case .dependentOperation = cancel(s,a,craft) {} else { assertionFailure("dependent craft undo allowed") }
assert(owned(s,b).count==1 && s.appearance(accountId:a).stars==75)
if case .success = cancel(s,b,operations(s,b).first { $0.operationEventId==send.operationEventId }!) {} else { assertionFailure("receiver undo") }
assert(owned(s,b).isEmpty && owned(s,a).count==1 && s.appearance(accountId:a).stars==100)
assert(!operations(s,a).contains { $0.operationEventId==send.operationEventId })
if case .success = cancel(s,a,craft) {} else { assertionFailure("craft undo after transfer undo") }
assert(Set(owned(s,a).map { $0.identifier })==Set([one.identifier,two.identifier]))
assert(s.appearance(accountId:a).giftOrder==[two.identifier,one.identifier])
assert(s.appearance(accountId:a).gramCardGiftIds==[one.identifier] && s.appearance(accountId:a).gramCardBackgroundId==one.identifier)
assert(s.appearance(accountId:a).emojiStatus != nil)
if case .notFound = cancel(s,a,craft) {} else { assertionFailure("double rollback") }

// Failure consumes all inputs and can restore them; no invented result.
let failure=VisualGramLocalAppearance();failure.values["10"] = .init(enabled:true,gifts:[one,two],stars:100)
if case .failure(.craftFailed) = failure.craftLocalGifts(accountId:a,references:[one.reference(accountId:a)],attributes:attrs,attributePermilles:probabilities,now:300,random:{$0.upperBound-1}) {} else { assertionFailure("failure case") }
let failed=operations(failure,a).first { $0.operationKind == .craft && $0.operationEventId != nil }!
assert(failed.operationSucceeded==false && failed.operationResult==nil && failed.operationInputs?.count==1)
if case .success = cancel(failure,a,failed) {} else { assertionFailure("failed craft rollback") }
assert(owned(failure,a).count==2)

// Real upgrade keeps its instance ID, but now has a separate event and a reversible generic input.
let upgrade=VisualGramLocalAppearance()
let ordinary=VisualGramGift(gift:.generic(.init(id:42,title:"Cake",availability:nil,releasedBy:nil)),counterpartyId:20,date:50,text:"caption")
upgrade.values["10"] = .init(enabled:true,gifts:[ordinary],stars:100)
upgrade.values["10"]?.giftOrder=[ordinary.identifier]
assert(upgrade.upgradeLocalGift(accountId:a,reference:ordinary.reference(accountId:a),preview:.init(attributes:[.model(1),.pattern(2),.backdrop(3)]),keepOriginalInfo:true,template:nft(42)) != nil)
assert(upgrade.appearance(accountId:a).stars==75 && upgrade.appearance(accountId:a).starsHistory?.last?.amount == -25)
let upgraded=operations(upgrade,a).first { $0.operationKind == .upgrade }!
assert(upgraded.operationInputs?.count==1 && upgraded.operationResult != nil && upgraded.date != ordinary.date)
let upgradeReload=VisualGramLocalAppearance();upgradeReload.values=try! JSONDecoder().decode([String:VisualGramAppearance].self,from:JSONEncoder().encode(upgrade.values))
assert(operations(upgradeReload,a).contains { $0.operationKind == .upgrade }, "upgrade kind lost after restart")
if case .success = cancel(upgrade,a,upgraded) {} else { assertionFailure("upgrade rollback") }
assert(owned(upgrade,a).first?.gift==ordinary.gift && owned(upgrade,a).first?.text=="caption")
assert(upgrade.appearance(accountId:a).stars==100 && upgrade.appearance(accountId:a).starsHistory?.isEmpty != false)
assert(upgrade.appearance(accountId:a).giftOrder==[ordinary.identifier], "upgrade rollback lost unchanged custom order")

// Sending a crafted asset by import is a delivery, never a new craft. Mirrored operation cancellation removes both chat records.
let imported=VisualGramLocalAppearance();var outgoing=one;outgoing.localIdentifier="sent-copy";outgoing.direction = .sent;outgoing.counterpartyId=20;outgoing.isCrafted=true
imported.addGift(accountId:a,targetPeerId:a,gift:outgoing)
let sent=operations(imported,a).first { $0.operationEventId != nil }!
assert(sent.operationKind == .sent && operations(imported,b).first?.operationKind == .received)
if case .success = cancel(imported,a,sent) {} else { assertionFailure("send rollback") }
assert(imported.appearance(accountId:a).gifts.isEmpty && imported.appearance(accountId:b).gifts.isEmpty)

// Batch gifts undo independently and preserve unrelated later gifts/profile changes.
let batch=VisualGramLocalAppearance()
batch.addGifts(accountId:a,targetPeerId:a,gifts:[one,two])
let firstReceive=operations(batch,a).first { $0.operationSourceId==one.identifier }!
batch.update(accountId:a) { $0.premium=true }
if case .success = cancel(batch,a,firstReceive) {} else { assertionFailure("batch cancellation") }
assert(owned(batch,a).map { $0.identifier }==[two.identifier] && batch.appearance(accountId:a).premium)

// Purchase undo restores both owners, refunds fee/currency, removes only the transaction's ledger entries.
let shop=VisualGramLocalAppearance();var listing=one;listing.resaleStars=40
shop.values["10"] = .init(enabled:true,gifts:[],stars:200)
shop.values["20"] = .init(enabled:true,gifts:[listing],stars:20)
assert(shop.buyLocalGift(accountId:a,recipientPeerId:a,gift:nft(1),price:40,requireListing:true,now:400) == .success)
let purchase=operations(shop,a).first { $0.operationEventId != nil && $0.operationKind == .purchase }!
shop.update(accountId:a) { $0.stars=($0.stars ?? 0)+10 }
if case .success = cancel(shop,a,purchase) {} else { assertionFailure("purchase rollback") }
assert(shop.appearance(accountId:a).stars==210 && shop.appearance(accountId:b).stars==20)
assert(owned(shop,a).isEmpty && owned(shop,b).first?.identifier==one.identifier)
assert(shop.appearance(accountId:a).starsHistory?.isEmpty != false)

// A refund cannot remove money already spent by a seller, and failure changes no other participant.
let conflict=VisualGramLocalAppearance();var sale=one;sale.resaleStars=40
conflict.values["10"] = .init(enabled:true,gifts:[],stars:200)
conflict.values["20"] = .init(enabled:true,gifts:[sale],stars:20)
assert(conflict.buyLocalGift(accountId:a,recipientPeerId:a,gift:nft(1),price:40,requireListing:true,now:401) == .success)
let conflicted=operations(conflict,a).first { $0.operationEventId != nil }!
conflict.update(accountId:b) { $0.stars=0 }
if case .balanceChanged = cancel(conflict,a,conflicted) {} else { assertionFailure("negative seller balance") }
assert(conflict.appearance(accountId:a).stars==160 && owned(conflict,a).count==1)

// GRAM purchases/refunds leave Stars unchanged.
let grams=VisualGramLocalAppearance();let gramAsset=nft(5,grams:1_000_000_000)
var gramListing=VisualGramGift(gift:.unique(gramAsset),counterpartyId:nil,date:1,text:"");gramListing.resaleGrams=1_000_000_000
var gramBuyer=VisualGramAppearance(enabled:true,gifts:[],stars:100);gramBuyer.grams=3_000_000_000
gramBuyer.gramHistory=[];grams.values["10"]=gramBuyer
var gramSeller=VisualGramAppearance(enabled:true,gifts:[gramListing],stars:20);gramSeller.grams=0;grams.values["20"]=gramSeller
assert(grams.buyLocalGiftWithGrams(accountId:a,recipientPeerId:a,gift:gramAsset,price:1_000_000_000,requireListing:true,now:500) == .success)
let gramPurchase=operations(grams,a).first { $0.operationEventId != nil }!
if case .success = cancel(grams,a,gramPurchase) {} else { assertionFailure("GRAM rollback") }
assert(grams.appearance(accountId:a).grams==3_000_000_000 && grams.appearance(accountId:b).grams==0 && grams.appearance(accountId:a).stars==100)

// Ordinary gift purchase rolls back the count, payment and both chat copies.
let ordinaryShop=VisualGramLocalAppearance();ordinaryShop.values["10"] = .init(enabled:true,gifts:[],stars:100)
let bear=StarGift.Gift(id:42,title:"Bear",availability:nil,releasedBy:nil)
assert(ordinaryShop.buyLocalOrdinaryGift(accountId:a,recipientPeerId:b,gift:bear,text:"hello",includeUpgrade:false,preview:nil,now:600) == .success)
let bearPurchase=operations(ordinaryShop,a).first { $0.operationEventId != nil }!
if case .success = cancel(ordinaryShop,a,bearPurchase) {} else { assertionFailure("ordinary purchase rollback") }
assert(ordinaryShop.appearance(accountId:a).stars==100 && (ordinaryShop.appearance(accountId:a).giftPurchaseCounts?["42"] ?? 0)==0)
assert(owned(ordinaryShop,b).isEmpty && ordinaryShop.appearance(accountId:a).gifts.isEmpty)

// Editing receipt parties/date/caption keeps the event reversible and mirrors in sync.
let edited=VisualGramLocalAppearance();var editable=one;editable.localIdentifier="editable";editable.direction = .sent;editable.counterpartyId=20
edited.addGift(accountId:a,targetPeerId:a,gift:editable)
let incomingEvent=operations(edited,b).first { $0.operationEventId != nil }!
assert(edited.editGiftDetails(accountId:a,targetPeerId:b,identifier:incomingEvent.identifier,history:true,counterpartyId:30,date:888,text:"new caption"))
assert(operations(edited,c).first?.operationSenderId==30 && operations(edited,b).first?.operationRecipientId==20)
let editedEvent=operations(edited,b).first { $0.operationEventId==incomingEvent.operationEventId }!
if case .success = cancel(edited,b,editedEvent) {} else { assertionFailure("edited event rollback") }
assert(edited.appearance(accountId:b).gifts.isEmpty && edited.appearance(accountId:c).gifts.isEmpty)

// Legacy classification is repaired, but missing old undo data is never fabricated.
var legacy=VisualGramLocalAppearance.operationSnapshot(outgoing,kind:.craft)
legacy.operationEventId=nil
let old=VisualGramLocalAppearance();old.values["10"] = .init(enabled:true,gifts:[],stars:10)
old.values["10"]?.giftOperationHistory=[legacy]
assert(operations(old,a).first?.operationKind != .craft)
if case .legacyUnavailable = cancel(old,a,legacy) {} else { assertionFailure("legacy undo fabricated") }

// Journal/undo survive JSON persistence, cosmetic edits and activation gating.
let persisted=VisualGramLocalAppearance();persisted.addGift(accountId:a,targetPeerId:a,gift:one)
let record=operations(persisted,a).first { $0.operationEventId != nil }!
let restored=VisualGramLocalAppearance();restored.values=try! JSONDecoder().decode([String:VisualGramAppearance].self,from:JSONEncoder().encode(persisted.values))
restored.update(accountId:a) { $0.gifts[0].pinnedToTop=true; $0.gifts[0].text="edited" }
VisualGramActivation.shared.hasAccess=false
_ = cancel(restored,a,record);assert(restored.values["10"]?.gifts.count==1)
VisualGramActivation.shared.hasAccess=true
if case .success = cancel(restored,a,record) {} else { assertionFailure("persisted cancellation") }
assert(owned(restored,a).isEmpty)
print("PASS: event kind vs provenance; participants; success/failure craft inputs/results; real upgrade rollback; mirrored sends; dependent and double undo; batch isolation; purchase refunds; legacy safety; persistence and activation guards")
'''

if __name__=='__main__':
    with tempfile.TemporaryDirectory(prefix='visualgram-operations-') as folder:
        path=Path(folder)/'Operations.swift';path.write_text(source(),encoding='utf-8')
        executable=Path(folder)/'operations'
        subprocess.run(['xcrun','swiftc',str(path),'-o',str(executable)],check=True)
        subprocess.run([str(executable)],check=True)
