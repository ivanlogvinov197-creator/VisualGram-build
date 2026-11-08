import Foundation
import Postbox

public extension VisualGramLocalAppearance {
    func starsHistoryTransactions(accountId: EnginePeer.Id, mode: StarsTransactionsContext.Mode, peers: [Int64: EnginePeer], ton: Bool = false) -> [StarsContext.State.Transaction] {
        let value = self.appearance(accountId: accountId)
        return ((ton ? value.gramHistory : value.starsHistory) ?? []).reversed().sorted { $0.date > $1.date }.filter { entry in
            switch mode {
            case .all: return true
            case .incoming: return entry.amount > 0
            case .outgoing: return entry.amount < 0
            }
        }.map { entry in
            var flags: StarsContext.State.Transaction.Flags = []
            if entry.kind == .purchase || entry.kind == .sale, case .unique = entry.gift { flags.insert(.isStarGiftResale) }
            if entry.kind == .adjustment, entry.title == VisualGramGift.StarsTransaction.upgradeTitle, case .unique = entry.gift {
                flags.insert(.isStarGiftUpgrade)
            }
            let peer: StarsContext.State.Transaction.Peer
            if let id = entry.peerId, let resolved = peers[id] { peer = .peer(resolved) }
            else if entry.gift != nil || entry.kind == .adjustment, let own = peers[accountId.toInt64()] { peer = .peer(own) }
            else { peer = .premiumBot }
            return StarsContext.State.Transaction(
                flags: flags, id: (ton ? "vg-grams:" : "vg-stars:") + entry.id,
                count: CurrencyAmount(amount: StarsAmount(value: max(-Int64.max, entry.amount), nanos: 0), currency: ton ? .ton : .stars),
                date: entry.date, peer: peer, title: entry.title ?? (entry.kind == .adjustment && entry.amount < 0 ? (ton ? "Списание GRAM" : "Списание звёзд") : nil), description: nil, photo: nil,
                transactionDate: entry.date, transactionUrl: nil, paidMessageId: nil, giveawayMessageId: nil,
                media: [], subscriptionPeriod: nil, starGift: entry.gift, floodskipNumber: nil,
                starrefCommissionPermille: nil, starrefPeerId: nil, starrefAmount: nil, paidMessageCount: nil,
                premiumGiftMonths: nil, adsProceedsFromDate: nil, adsProceedsToDate: nil
            )
        }
    }
}
