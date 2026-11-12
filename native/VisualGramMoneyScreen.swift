import UIKit
import AccountContext
import AlertComponent
import AlertMultilineInputFieldComponent
import ComponentFlow
import Display
import PresentationDataUtils
import SwiftSignalKit
import TelegramCore
import TelegramPresentationData
import WalletContext

public func presentGramTopUp(on controller: ViewController, context: AccountContext, data: PresentationData) {
    let input = AlertMultilineInputFieldComponent.ExternalState()
    let alert = AlertScreen(
        configuration: .init(dismissOnOutsideTap: false, allowInputInset: true),
        content: [
            AnyComponentWithIdentity(id: "title", component: AnyComponent(AlertTitleComponent(title: data.strings.Wallet_AddFunds))),
            AnyComponentWithIdentity(id: "amount", component: AnyComponent(AlertMultilineInputFieldComponent(
                context: context,
                initialValue: NSAttributedString(string: ""),
                placeholder: data.strings.Wallet_Send_AmountPlaceholder,
                maxHeight: 56,
                returnKeyType: .done,
                keyboardType: .decimalPad,
                autocapitalizationType: .none,
                autocorrectionType: .no,
                isInitiallyFocused: true,
                externalState: input
            )))
        ],
        actions: [
            .init(title: data.strings.Common_Cancel),
            .init(title: data.strings.Wallet_AddFunds, type: .default, action: { [weak controller] in
                guard let controller else { return }
                let amount = VisualGramLocalAppearance.parseGrams(input.value.string) ?? 0
                if !VisualGramLocalAppearance.shared.topUpLocalGrams(accountId: context.account.peerId, amount: amount, now: Int32(clamping: Int64(Date().timeIntervalSince1970))) {
                    controller.present(textAlertController(context: context, title: nil, text: data.strings.Wallet_Transfer_ErrorText, actions: [
                        TextAlertAction(type: .defaultAction, title: data.strings.Common_OK, action: {})
                    ]), in: .window(.root))
                }
            })
        ],
        updatedPresentationData: (initial: data, signal: context.sharedContext.presentationData)
    )
    controller.present(alert, in: .window(.root))
}

public func visualGramWalletState(context: AccountContext) -> Signal<WalletContext.State, NoError> {
    let store = VisualGramLocalAppearance.shared
    let accountId = context.account.peerId
    return store.changes
    |> mapToSignal { _ -> Signal<WalletContext.State, NoError> in
        let appearance = store.appearance(accountId: accountId)
        let entries = appearance.enabled ? (appearance.gramHistory ?? []) : []
        let peerIds = Set(entries.compactMap { $0.peerId.map { EnginePeer.Id($0) } })
        let peers = context.engine.data.get(EngineDataMap(peerIds.map { TelegramEngine.EngineData.Item.Peer.Peer(id: $0) }))
        let card = store.displayWalletCard(accountId: accountId, peerId: accountId, server: nil, appearanceOverride: appearance)
        return peers |> map { peers in
            let transactions = entries.reversed().sorted { $0.date > $1.date }.map { entry -> WalletContext.Transaction in
                let peer = entry.peerId.flatMap { peers[EnginePeer.Id($0)] ?? nil }
                return WalletContext.Transaction(
                    id: "duckgram:" + entry.kind.rawValue + ":" + entry.id,
                    presentationId: entry.kind == .transfer ? "pending:" + entry.id : nil,
                    logicalTime: "",
                    timestamp: entry.date,
                    direction: entry.amount < 0 ? .outgoing : .incoming,
                    amount: entry.amount,
                    fee: 0,
                    peer: peer.map { .user($0, address: "", domain: nil) } ?? .unsupported,
                    comment: entry.comment
                )
            }
            let balance = appearance.enabled ? (appearance.grams ?? 0) : 0
            return WalletContext.State(
                phase: .wallet(.init(address: "", publicKey: "")),
                balance: .value(balance, updatedAt: Int32(clamping: Int64(Date().timeIntervalSince1970))),
                transactions: .init(items: transactions, offset: 0, canLoadMore: false, isLoadingMore: false, error: nil),
                pendingTransfers: [],
                activeOperation: nil,
                cardStickers: (card?.stickers ?? []).compactMap {
                    WalletContext.CardSticker(serverSticker: $0, backgroundNftAddress: card?.backgroundNft?.address)
                }
            )
        }
    }
}
