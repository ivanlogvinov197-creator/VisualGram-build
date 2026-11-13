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
    replace(shared, 'import WalletReceiveScreen\n', 'import WalletReceiveScreen\nimport WalletSendScreen\n')
    for suffix in ('', ', isOwnWallet: isOwnWallet', ', appeared: appeared'):
        replace(shared, 'return WalletReceiveScreen(context: context, address: address' + suffix + ')',
                'return WalletReceiveScreen(context: context, address: address' + suffix + ', visualTopUp: VisualGramLocalAppearance.visualWalletPeer(address: address) == context.account.peerId ? { controller in\n            presentGramTopUp(on: controller, context: context, data: context.sharedContext.currentPresentationData.with { $0 })\n        } : nil)')
    receive = ui / "Components/Wallet/WalletReceiveScreen/Sources/WalletReceiveScreen.swift"
    replace(receive, '        return State(context: self.context, isOwnWallet: self.isOwnWallet)', '        return State(context: self.context, isOwnWallet: self.isOwnWallet && self.visualTopUp == nil)')
    replace(receive, '    init(context: AccountContext, address: String, isOwnWallet: Bool) {', '    let visualTopUp: ((ViewController) -> Void)?\n\n    init(context: AccountContext, address: String, isOwnWallet: Bool, visualTopUp: ((ViewController) -> Void)?) {\n        self.visualTopUp = visualTopUp')
    replace(receive, 'public init(context: AccountContext, address: String, isOwnWallet: Bool = true, appeared: (() -> Void)? = nil) {', 'public init(context: AccountContext, address: String, isOwnWallet: Bool = true, appeared: (() -> Void)? = nil, visualTopUp: ((ViewController) -> Void)? = nil) {')
    replace(receive, 'component: WalletReceiveSheetComponent(context: context, address: address, isOwnWallet: isOwnWallet),', 'component: WalletReceiveSheetComponent(context: context, address: address, isOwnWallet: isOwnWallet, visualTopUp: visualTopUp),')
    replace(receive, '                        buy: { [weak componentState] in\n                            guard isOwnWallet else { return }', """                        buy: { [weak componentState, visualTopUp = context.component.visualTopUp] in
                            guard isOwnWallet else { return }
                            if let visualTopUp, let controller = controller() {
                                visualTopUp(controller)
                                return
                            }
""".rstrip())
    replace(receive, r'                        string: "ton://transfer/\(component.address)",', r'                        string: component.address.hasPrefix("dg") ? component.address : "ton://transfer/\(component.address)",')

    attachment = ui / "Sources/ChatControllerOpenAttachmentMenu.swift"
    replace(attachment, '            switch subject {\n            case .default, .gift:\n                if WalletConfiguration', '''            let hasLocalMoney = VisualGramLocalAppearance.shared.localGramBalance(accountId: self.context.account.peerId) != nil
            switch subject {
            case .default, .gift:
                if (hasLocalMoney || WalletConfiguration''')
    replace(attachment, ').isAvailable, !isScheduledMessages, banSendText', ').isAvailable), !isScheduledMessages, banSendText')
    replace(attachment, '                            allowOpenRecipientChat: false,\n', '                            visualGram: hasLocalMoney,\n                            allowOpenRecipientChat: false,\n')

    replace(attachment, 'walletTransferAnimationCoordinator().receive(id: id, source: source)', 'walletTransferAnimationCoordinator().receive(id: id, source: source, visualGram: hasLocalMoney)')
    replace(attachment, 'walletTransferAnimationCoordinator().prepare(id: id)', 'walletTransferAnimationCoordinator().prepare(id: id, visualGram: hasLocalMoney)')

    # Keep the stock glass animation, with the stock slide-in for an unavailable source.
    attachment_ui = root / "submodules/AttachmentUI/Sources/AttachmentController.swift"
    replace(attachment_ui, '        func animateIn() {\n', """        private func validAttachmentMorphFrame(_ frame: CGRect) -> Bool {
            return frame.origin.x.isFinite && frame.origin.y.isFinite
                && frame.width.isFinite && frame.height.isFinite
                && frame.width >= 1.0 && frame.height >= 1.0
        }

        private func attachmentMorphFrame(for button: UIView) -> CGRect? {
            let frame = button.convert(button.bounds, to: self.view)
            return self.validAttachmentMorphFrame(frame) ? frame : nil
        }

        func animateIn() {
""")
    replace(attachment_ui, '                if case .glass = controller.style, let attachmentButton = controller.attachmentButton {\n', """                let targetFrame = self.container.clipNode.view.convert(self.container.clipNode.view.bounds, to: self.view)
                if case .glass = controller.style, let attachmentButton = controller.attachmentButton,
                   let window = self.view.window, attachmentButton.window === window,
                   let sourceGlassView = findParentGlassBackgroundView(attachmentButton), let glassParams = sourceGlassView.params,
                   self.validAttachmentMorphFrame(targetFrame),
                   let sourceButtonFrame = self.attachmentMorphFrame(for: attachmentButton) {
""")
    source_text = attachment_ui.read_text(encoding="utf-8")
    start = source_text.index('                    let targetFrame =', source_text.index('        func animateIn()'))
    end = source_text.index('                } else {\n                    let targetPosition', start)
    original_morph = source_text[start:end]
    morph_body = original_morph.split('let glassParams = sourceGlassView.params {\n', 1)[1].rsplit('                    }\n', 1)[0]
    morph_body = '\n'.join(line[4:] if line.startswith('    ') else line for line in morph_body.split('\n'))
    replace(attachment_ui, original_morph, '                    let sourceButtonScale = sourceButtonFrame.width / targetFrame.width\n\n' + morph_body)
    replace(attachment_ui, '                if case .glass = controller.style, let attachmentButton = controller.attachmentButton, let sourceGlassView = appearanceTransition?.sourceGlassView ?? findParentGlassBackgroundView(attachmentButton), let glassParams = sourceGlassView.params {', """                let initialFrame = appearanceTransition?.targetFrame ?? self.container.clipNode.view.convert(self.container.clipNode.view.bounds, to: self.view)
                if case .glass = controller.style, let attachmentButton = controller.attachmentButton,
                   let window = self.view.window, attachmentButton.window === window,
                   let sourceGlassView = appearanceTransition?.sourceGlassView ?? findParentGlassBackgroundView(attachmentButton),
                   let glassParams = sourceGlassView.params, self.validAttachmentMorphFrame(initialFrame),
                   let targetButtonFrame = self.attachmentMorphFrame(for: attachmentButton) {""")
    replace(attachment_ui, """                    let initialFrame = appearanceTransition?.targetFrame ?? self.container.clipNode.view.convert(self.container.clipNode.view.bounds, to: self.view)

                    let targetButtonFrame = attachmentButton.convert(attachmentButton.bounds, to: self.view)
""", '')
    replace(attachment, '                var (buttons, allButtons, initialButton) = buttonsAndInitialButton\n', '                guard strongSelf.attachmentController == nil else { return }\n                var (buttons, allButtons, initialButton) = buttonsAndInitialButton\n')
    replace(attachment, '                    if !premiumGiftOptions.isEmpty {\n                        buttons.insert(.gift, at: 1)\n', '                    if !premiumGiftOptions.isEmpty && !buttons.contains(.gift) {\n                        buttons.insert(.gift, at: min(1, buttons.count))\n')
    replace(attachment, '                    buttons.insert(.richText, at: firstBotIndex)\n', '                    if !buttons.contains(.richText) {\n                        buttons.insert(.richText, at: firstBotIndex)\n                    }\n')
    replace(attachment, '                let present = {\n                    attachmentController.navigationPresentation', '                let present = {\n                    guard strongSelf.attachmentController === attachmentController else { return }\n                    guard strongSelf.viewIfLoaded?.window != nil else {\n                        strongSelf.attachmentController = nil\n                        strongSelf.canReadHistory.set(true)\n                        return\n                    }\n                    attachmentController.navigationPresentation')
    replace(attachment, '                attachmentController.didDismiss = { [weak self] in\n                    self?.attachmentController = nil\n                    self?.canReadHistory.set(true)\n                }', """                attachmentController.didDismiss = { [weak self, weak attachmentController] in
                    guard let self, self.attachmentController === attachmentController else { return }
                    self.attachmentController = nil
                    self.canReadHistory.set(true)
                }""")
    replace(attachment, '                if inputIsActive {\n                    Queue.mainQueue().after(0.15, {\n                        present()', '                strongSelf.attachmentController = attachmentController\n                if inputIsActive {\n                    Queue.mainQueue().after(0.15, {\n                        present()')

    entries = ui / "Sources/ChatHistoryEntriesForView.swift"
    replace(entries, '        if !messages.isEmpty {\n            entries.append(contentsOf: messages.map {', '        if !messages.isEmpty {\n            if view.entries.isEmpty {\n                entries.removeAll { entry in\n                    if case .ChatInfoEntry = entry { return true }\n                    return false\n                }\n            }\n            entries.append(contentsOf: messages.map {')

    history = ui / "Sources/ChatHistoryListNode.swift"
    replace(history, 'let isEmpty = transition.historyView.originalView.entries.isEmpty || loadState == .empty(.botInfo)', 'let isEmpty = loadState == .empty(.botInfo) || (transition.historyView.originalView.entries.isEmpty && !transition.historyView.filteredEntries.contains { entry in\n                if case let .MessageEntry(message, _, _, _, _, _) = entry { return message.id.namespace == Int32.max - 42 }\n                return false\n            })', expected=2)

    root_controller = ui / "Sources/TelegramRootController.swift"
    replace(root_controller, '        let newsController = NewsScreen(context: self.context)\n        \n        var controllers: [ViewController] = []', """        let newsController = NewsScreen(context: self.context)
        let contactsController = ContactsController(context: self.context)
        contactsController.isTab = true
        self.contactsController = contactsController

        var controllers: [ViewController] = [contactsController]""")
    replace(root_controller, '        var controllers: [ViewController] = []\n        if showCallsTab {', '        var controllers: [ViewController] = []\n        if let contactsController = self.contactsController {\n            controllers.append(contactsController)\n        }\n        if showCallsTab {')
    replace(root_controller, '        if let index = rootTabController.controllers.firstIndex(where: { $0 is PeerInfoScreenImpl }) {\n            rootTabController.selectedIndex = index\n        }\n        \n        let contactsController = ContactsController(context: self.context)\n        self.contactsController = contactsController\n        self.pushViewController(contactsController)', '        if let index = rootTabController.controllers.firstIndex(where: { $0 is ContactsController }) {\n            rootTabController.selectedIndex = index\n        }')
    replace(root_controller, '    /// Contacts has no tab: the Settings tab, with the screen Settings ▸ Contacts pushes over it.\n', '')
    contacts = root / "submodules/ContactListUI/Sources/ContactsController.swift"
    replace(contacts, 'public class ContactsController: ViewController {\n', 'public class ContactsController: ViewController {\n    public var isTab = false\n')
    replace(contacts, '        self.title = self.presentationData.strings.Contacts_Title\n', """        self.title = self.presentationData.strings.Contacts_Title
        self.tabBarItem.title = self.title
        let icon = UIImage(bundleImageName: "Chat List/Tabs/IconContacts")
        self.tabBarItem.image = icon
        self.tabBarItem.selectedImage = icon
        self.tabBarItem.animationName = self.presentationData.reduceMotion ? nil : "TabContacts"
""", expected=2)
    contacts_node = root / "submodules/ContactListUI/Sources/ContactsControllerNode.swift"
    replace(contacts_node, '        let backPressed: (() -> Void)? = { [weak self] in\n', '        let backPressed: (() -> Void)? = self.controller?.isTab == true ? nil : { [weak self] in\n')

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
                                    peer: peer.map { .user($0, address: peerAddress.isEmpty ? VisualGramLocalAppearance.visualWalletAddress(peerId: $0.id) : peerAddress, domain: nil) } ?? .unsupported,
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
