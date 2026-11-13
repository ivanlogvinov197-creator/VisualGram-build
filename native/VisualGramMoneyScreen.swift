import Foundation
import AccountContext
import SwiftSignalKit
import TelegramCore
import WalletContext

public func visualGramTransferAddress(_ input: String) -> String? {
    let input = input.trimmingCharacters(in: .whitespacesAndNewlines)
    if let peerId = VisualGramLocalAppearance.visualWalletPeer(address: input) {
        return VisualGramLocalAppearance.visualWalletAddress(peerId: peerId)
    }
    return WalletContext.transferRecipient(from: input)?.address
}

public func initialVisualGramWalletState(context: AccountContext) -> WalletContext.State {
    let accountId = context.account.peerId
    let appearance = VisualGramLocalAppearance.shared.appearance(accountId: accountId)
    return makeVisualGramWalletState(accountId: accountId, appearance: appearance, transactions: [])
}

private func makeVisualGramWalletState(accountId: EnginePeer.Id, appearance: VisualGramAppearance, transactions: [WalletContext.Transaction]) -> WalletContext.State {
    let card = VisualGramLocalAppearance.shared.displayWalletCard(accountId: accountId, peerId: accountId, server: nil, appearanceOverride: appearance)
    let balance = appearance.enabled ? (appearance.grams ?? 0) : 0
    return WalletContext.State(
        phase: .wallet(.init(address: VisualGramLocalAppearance.visualWalletAddress(peerId: accountId), publicKey: "")),
        balance: .value(balance, updatedAt: Int32(clamping: Int64(Date().timeIntervalSince1970))),
        transactions: .init(items: transactions, offset: 0, canLoadMore: false, isLoadingMore: false, error: nil),
        pendingTransfers: [],
        activeOperation: nil,
        cardStickers: (card?.stickers ?? []).compactMap {
            WalletContext.CardSticker(serverSticker: $0, backgroundNftAddress: card?.backgroundNft?.address)
        }
    )
}

public func visualGramWalletState(context: AccountContext) -> Signal<WalletContext.State, NoError> {
    let store = VisualGramLocalAppearance.shared
    let accountId = context.account.peerId
    return store.changes
    |> mapToSignal { _ -> Signal<WalletContext.State, NoError> in
        let appearance = store.appearance(accountId: accountId)
        let entries = appearance.enabled ? VisualGramBalanceHistory.grams.displayedEntries(in: appearance) : []
        let peerIds = Set(entries.compactMap { $0.peerId.map { EnginePeer.Id($0) } })
        let peers = context.engine.data.get(EngineDataMap(peerIds.map { TelegramEngine.EngineData.Item.Peer.Peer(id: $0) }))
        return peers |> map { peers in
            let transactions = entries.map { entry -> WalletContext.Transaction in
                let peer = entry.peerId.flatMap { peers[EnginePeer.Id($0)] ?? nil }
                let peerId = entry.peerId.map { EnginePeer.Id($0) }
                    ?? entry.walletAddress.flatMap { VisualGramLocalAppearance.visualWalletPeer(address: $0) }
                let address = peerId.map { VisualGramLocalAppearance.visualWalletAddress(peerId: $0) } ?? entry.walletAddress
                let counterparty: WalletContext.Transaction.Peer
                if let peer, let address {
                    counterparty = .user(peer, address: address, domain: nil)
                } else if let address {
                    counterparty = .address(address, domain: nil)
                } else {
                    counterparty = .unsupported
                }
                return WalletContext.Transaction(
                    id: "duckgram:" + entry.kind.rawValue + ":" + entry.id,
                    presentationId: entry.kind == .transfer ? "pending:" + entry.id : nil,
                    logicalTime: "",
                    timestamp: entry.date,
                    direction: entry.amount < 0 ? .outgoing : .incoming,
                    amount: entry.amount,
                    fee: 0,
                    peer: counterparty,
                    comment: entry.comment
                )
            }
            return makeVisualGramWalletState(accountId: accountId, appearance: appearance, transactions: transactions)
        }
    }
}
