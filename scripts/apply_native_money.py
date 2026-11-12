"""Route DuckGram's local GRAM balance through the Telegram wallet entry points."""
import shutil

from prepare_native import replace
from apply_native_wallet_ui import apply_wallet_dashboard, apply_wallet_send


def apply_money(root, project):
    ui = root / "submodules/TelegramUI"
    wallet_send = ui / "Components/Wallet/WalletSendScreen"
    shutil.copyfile(project / "native/VisualGramMoneyScreen.swift", wallet_send / "Sources/VisualGramMoneyScreen.swift")
    apply_wallet_send(wallet_send)
    apply_wallet_dashboard(ui)
    shared = ui / "Sources/SharedAccountContext.swift"
    replace(shared, '            opensCollectibles: opensCollectibles\n',
            '            opensCollectibles: opensCollectibles,\n            visualGram: VisualGramLocalAppearance.shared.localGramBalance(accountId: context.account.peerId) != nil\n')

    replace(shared, 'WalletTransactionScreen(context: context, transaction: transaction, fromChat: fromChat, decryptCommentOnOpen:', 'WalletTransactionScreen(context: context, transaction: transaction, fromChat: fromChat, visualGram: transaction.id.hasPrefix("duckgram:"), decryptCommentOnOpen:')
    attachment = ui / "Sources/ChatControllerOpenAttachmentMenu.swift"
    replace(attachment, '            switch subject {\n            case .default, .gift:\n                if WalletConfiguration', '''            let hasLocalMoney = VisualGramLocalAppearance.shared.localGramBalance(accountId: self.context.account.peerId) != nil
            switch subject {
            case .default, .gift:
                if (hasLocalMoney || WalletConfiguration''')
    replace(attachment, ').isAvailable, !isScheduledMessages, banSendText', ').isAvailable), !isScheduledMessages, banSendText')
    replace(attachment, '                            allowOpenRecipientChat: false,\n', '                            visualGram: hasLocalMoney,\n                            allowOpenRecipientChat: false,\n')

    replace(attachment, 'walletTransferAnimationCoordinator().receive(id: id, source: source)', 'walletTransferAnimationCoordinator().receive(id: id, source: source, visualGram: hasLocalMoney)')
    replace(attachment, 'walletTransferAnimationCoordinator().prepare(id: id)', 'walletTransferAnimationCoordinator().prepare(id: id, visualGram: hasLocalMoney)')

    peer_info = ui / "Components/PeerInfo/PeerInfoScreen/Sources"
    menu = peer_info / "PeerInfoScreenPerformButtonAction.swift"
    replace(menu, '                    if WalletConfiguration.with(appConfiguration: strongSelf.context.currentAppConfiguration.with { $0 }).isAvailable, strongSelf.peerId.namespace', '''                    let hasLocalMoney = VisualGramLocalAppearance.shared.localGramBalance(accountId: strongSelf.context.account.peerId) != nil
                    if (hasLocalMoney || WalletConfiguration.with(appConfiguration: strongSelf.context.currentAppConfiguration.with { $0 }).isAvailable), strongSelf.peerId.namespace''')
    replace(menu, 'peer: peer, walletContext: walletContext, allowOpenRecipientChat: false, completed:', 'peer: peer, walletContext: walletContext, visualGram: hasLocalMoney, allowOpenRecipientChat: false, completed:')

    profile = peer_info / "PeerInfoScreen.swift"
    replace(profile, '                if peer.id == self.context.account.peerId {\n                    guard WalletConfiguration', '''                let accountId = self.context.account.peerId
                let store = VisualGramLocalAppearance.shared
                let hasLocalMoney = store.localGramBalance(accountId: accountId) != nil
                if peer.id == accountId {
                    if hasLocalMoney {
                        peerWalletScreen.openScreen(self.context.sharedContext.makeWalletScreen(context: self.context))
                        return
                    }
                    guard WalletConfiguration''')
    replace(profile, '''                let localWallet = VisualGramLocalAppearance.shared.appearance(accountId: self.context.account.peerId, targetPeerId: peer.id)
                if localWallet.enabled && localWallet.grams != nil { return }
''', '''                if hasLocalMoney, let walletContext = self.context.walletContext {
                    let screen = WalletSendScreen(context: self.context, peer: peer, walletContext: walletContext, visualGram: true, completed: { [weak self] in
                        self?.openVisualGramMoneyChat(peer)
                    })
                    screen.navigationPresentation = .modal
                    peerWalletScreen.openScreen(screen)
                    return
                }
''')
    with profile.open("a", encoding="utf-8", newline="\n") as output:
        output.write('''
extension PeerInfoScreenNode {
    func openVisualGramMoneyChat(_ peer: EnginePeer) {
        guard let navigationController = self.controller?.navigationController as? NavigationController else { return }
        self.context.sharedContext.navigateToChatController(NavigateToChatControllerParams(navigationController: navigationController, context: self.context, chatLocation: .peer(peer), keepStack: .default, useExisting: true, completion: { chatController in
            chatController.scrollToEndOfHistory()
        }))
    }
}
''')

    card = ui / "Components/Wallet/PeerWalletScreen/Sources/PeerWalletScreen.swift"
    replace(card, '''            let noticeString: String?
            if component.peer.id == component.context.account.peerId {''', '''            let accountId = component.context.account.peerId
            let store = VisualGramLocalAppearance.shared
            let target = store.appearance(accountId: accountId, targetPeerId: component.peer.id)
            let isLocalCard = target.enabled && target.grams != nil
            let hasLocalMoney = store.localGramBalance(accountId: accountId) != nil
            let noticeString: String?
            if isLocalCard {
                noticeString = nil
            } else if component.peer.id == component.context.account.peerId {''')
    replace(card, '            let showsWalletInfo = !isOwnWallet && !state.hasOwnWallet\n',
            '            let showsWalletInfo = !isOwnWallet && !state.hasOwnWallet && !hasLocalMoney && !isLocalCard\n')
    replace(card, '                    isEnabled: isOwnWallet || showsWalletInfo || (component.context.walletContext != nil && state.card != nil),\n',
            '                    isEnabled: isOwnWallet || hasLocalMoney || isLocalCard || showsWalletInfo || (component.context.walletContext != nil && state.card != nil),\n')

    settings = peer_info / "PeerInfoSettingsItems.swift"
    replace(settings, '''        if WalletConfiguration.with(appConfiguration: context.currentAppConfiguration.with { $0 }).isAvailable {
            let balanceText: NSAttributedString
            if let balance = settings.walletBalance, balance > 10_000_000 {''', '''        let localGramBalance = VisualGramLocalAppearance.shared.localGramBalance(accountId: context.account.peerId)
        if localGramBalance != nil || WalletConfiguration.with(appConfiguration: context.currentAppConfiguration.with { $0 }).isAvailable {
            let balanceText: NSAttributedString
            if let balance = localGramBalance {
                balanceText = NSAttributedString(string: formatTonAmountText(balance, dateTimeFormat: presentationData.dateTimeFormat), font: Font.regular(17.0), textColor: presentationData.theme.list.itemSecondaryTextColor)
            } else if let balance = settings.walletBalance, balance > 10_000_000 {''')
    settings_action = peer_info / "PeerInfoScreenSettingsActions.swift"
    replace(settings_action, '        case .wallet:\n', '''        case .wallet:
            if VisualGramLocalAppearance.shared.localGramBalance(accountId: self.context.account.peerId) != nil {
                push(self.context.sharedContext.makeWalletScreen(context: self.context))
                return
            }
''')

    transfer_bubble = ui / "Components/Chat/ChatMessageTransferBubbleContentNode/Sources/ChatMessageTransferBubbleContentNode.swift"
    replace(transfer_bubble, '                let fiatState = item.context.walletContext?.stateValue.fiat\n', '''                let localTransfer = engineMessage.id.namespace == Int32.max - 42
                let fiatState = localTransfer ? nil : item.context.walletContext?.stateValue.fiat
''')
    replace(transfer_bubble, '        let walletContext = item.context.walletContext\n        if self.walletContext !== walletContext {', '''        if item.message.id.namespace == Int32.max - 42 {
            self.walletStateDisposable?.dispose()
            self.walletStateDisposable = nil
            self.walletContext = nil
            self.renderedFiatState = nil
            self.updateTransferStatus(.completed, animated: false)
            return
        }
        let walletContext = item.context.walletContext
        if self.walletContext !== walletContext {''')
    replace(transfer_bubble, '                    maxDecimalPositions: 3',
            '                    maxDecimalPositions: localTransfer ? 9 : 3', expected=2)
    replace(transfer_bubble, '        maxDecimalPositions: 3,\n        formatString: strings.Currency_Grams',
            '        maxDecimalPositions: message.id.namespace == Int32.max - 42 ? 9 : 3,\n        formatString: strings.Currency_Grams')
    chat = ui / "Sources/ChatController.swift"
    replace(chat, '                        case let .gramTransfer(amount, peerAddress, transactionId, messageComment, commentEncrypted):\n', '''                        case let .gramTransfer(amount, peerAddress, transactionId, messageComment, commentEncrypted):
                            if message.id.namespace == Int32.max - 42 {
                                let incoming = message.flags.contains(.Incoming)
                                let peer = message.peers[message.id.peerId].flatMap(EnginePeer.init)
                                let transaction = WalletContext.Transaction(
                                    id: "duckgram:transfer:" + transactionId,
                                    logicalTime: "",
                                    timestamp: message.timestamp,
                                    direction: incoming ? .incoming : .outgoing,
                                    amount: incoming ? amount : -amount,
                                    fee: 0,
                                    peer: peer.map { .user($0, address: "", domain: nil) } ?? .unsupported,
                                    comment: messageComment
                                )
                                self.push(self.context.sharedContext.makeWalletTransactionScreen(context: self.context, transaction: transaction, fromChat: true, decryptCommentOnOpen: false))
                                return true
                            }
''')
    context_menu = ui / "Sources/Chat/ChatControllerOpenMessageContextMenu.swift"
    replace(context_menu, '            let alert = textAlertController(context: self.context, title: "Удалить подарок из чата?", text: "Карточка исчезнет из переписки. Подарок останется в профиле владельца.", actions: actions, actionLayout: .vertical)\n', '''            let isGramTransfer = message.media.contains { media in
                if let action = media as? TelegramMediaAction, case .gramTransfer = action.action { return true }
                return false
            }
            let title = isGramTransfer ? self.presentationData.strings.Conversation_ContextMenuDelete : "Удалить подарок из чата?"
            let text = isGramTransfer ? "" : "Карточка исчезнет из переписки. Подарок останется в профиле владельца."
            let alert = textAlertController(context: self.context, title: title, text: text, actions: actions, actionLayout: .vertical)
''')

    preview = root / "submodules/ChatListUI/Sources/Node/ChatListItemStrings.swift"
    list_item = preview.with_name("ChatListItem.swift")
    replace(list_item, '                let hasUnreadIncomingGramTransfer = messages.last.map { message in\n',
            '                let hasUnreadIncomingGramTransfer = messages.last.map { message in\n                    guard message.id.namespace != Int32.max - 42 else { return false }\n')

    animation = ui / "Sources/ChatWalletTransferAnimation.swift"
    replace(animation, '            let matches: Bool\n', '''            if message.id.namespace == Int32.max - 42 {
                return message.media.contains { media in
                    guard let action = media as? TelegramMediaAction,
                          case let .gramTransfer(_, _, transactionId, _, _) = action.action else { return false }
                    return transactionId == self.operationId
                }
            }
            let matches: Bool
''')

    replace(animation, '        let operationId: String\n', '        let operationId: String\n        let visualGram: Bool\n')
    replace(animation, '        init(id: String, peerId: EnginePeer.Id) {', '        init(id: String, peerId: EnginePeer.Id, visualGram: Bool) {\n            self.visualGram = visualGram')
    replace(animation, '            if message.id.namespace == Int32.max - 42 {', '            if self.visualGram && message.id.namespace == Int32.max - 42 {')
    replace(animation, '    func prepare(id: String) {', '    func prepare(id: String, visualGram: Bool = false) {')
    replace(animation, '    func receive(id: String, source: WalletSendTransferAnimationSource?) -> Bool {', '    func receive(id: String, source: WalletSendTransferAnimationSource?, visualGram: Bool = false) -> Bool {')
    replace(animation, """              let controller = self.controller, let peerId = controller.chatLocation.peerId,
              let state = controller.context.walletContext?.stateValue,
              let transaction = state.transactions.items.first(where: { $0.presentationId == id }),
              transaction.status != .failed else { return }
        let flight = Flight(id: id, peerId: peerId)
        self.refresh(flight, state: state)""", """              let controller = self.controller, let peerId = controller.chatLocation.peerId else { return }
        let state = visualGram ? nil : controller.context.walletContext?.stateValue
        guard visualGram || state?.transactions.items.contains(where: { $0.presentationId == id && $0.status != .failed }) == true else { return }
        let flight = Flight(id: id, peerId: peerId, visualGram: visualGram)
        if let state { self.refresh(flight, state: state) }""")
    replace(animation, """              let peerId = controller.chatLocation.peerId,
              let wallet = controller.context.walletContext,
              let transaction = wallet.stateValue.transactions.items.first(where: { $0.presentationId == id }),
              transaction.status != .failed, let source, let window = source.window,""", """              let peerId = controller.chatLocation.peerId,
              (visualGram || controller.context.walletContext?.stateValue.transactions.items.contains(where: { $0.presentationId == id && $0.status != .failed }) == true),
              let source, let window = source.window,""")
    replace(animation, '        let flight = self.flights[id] ?? Flight(id: id, peerId: peerId)\n', '        let flight = self.flights[id] ?? Flight(id: id, peerId: peerId, visualGram: visualGram)\n')
    replace(animation, '        self.refresh(flight, state: wallet.stateValue)\n', '        if !visualGram, let state = controller.context.walletContext?.stateValue { self.refresh(flight, state: state) }\n')
    replace(animation, """            guard let state = controller.context.walletContext?.stateValue else {
                self.cancel(id: id, animated: false)
                continue
            }
            self.refresh(flight, state: state)
            let transaction = state.transactions.items.first(where: { $0.presentationId == id })
            let hasPending = state.pendingTransfers.contains(where: { $0.id == flight.operationId })
            guard !UIAccessibility.isReduceMotionEnabled, flight.peerId == controller.chatLocation.peerId,
                  transaction?.status != .failed, transaction != nil || hasPending else {""", """            let state = flight.visualGram ? nil : controller.context.walletContext?.stateValue
            if let state { self.refresh(flight, state: state) }
            let transaction = state?.transactions.items.first(where: { $0.presentationId == id })
            let hasPending = state?.pendingTransfers.contains(where: { $0.id == flight.operationId }) == true
            guard !UIAccessibility.isReduceMotionEnabled, flight.peerId == controller.chatLocation.peerId,
                  flight.visualGram || (transaction?.status != .failed && (transaction != nil || hasPending)) else {""")
