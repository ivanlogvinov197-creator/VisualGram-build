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
                'return WalletReceiveScreen(context: context, address: address' + suffix + ', visualGram: VisualGramLocalAppearance.visualWalletPeer(address: address) != nil)')
    receive = ui / "Components/Wallet/WalletReceiveScreen/Sources/WalletReceiveScreen.swift"
    replace(receive, '    let isPurchaseInProgress: Bool\n', '    let visualGram: Bool\n    let isPurchaseInProgress: Bool\n')
    replace(receive, '        isPurchaseInProgress: Bool,\n', '        visualGram: Bool,\n        isPurchaseInProgress: Bool,\n')
    replace(receive, '        self.isPurchaseInProgress = isPurchaseInProgress', '        self.visualGram = visualGram\n        self.isPurchaseInProgress = isPurchaseInProgress')
    replace(receive, '        if lhs.isPurchaseInProgress != rhs.isPurchaseInProgress {', '        if lhs.visualGram != rhs.visualGram || lhs.isPurchaseInProgress != rhs.isPurchaseInProgress {')
    replace(receive, '                        isEnabled: !component.isPurchaseInProgress,', '                        isEnabled: !component.visualGram && !component.isPurchaseInProgress,')
    replace(receive, '        return State(context: self.context, isOwnWallet: self.isOwnWallet)', '        return State(context: self.context, isOwnWallet: self.isOwnWallet && !self.visualGram)')
    replace(receive, '    init(context: AccountContext, address: String, isOwnWallet: Bool) {', '    let visualGram: Bool\n\n    init(context: AccountContext, address: String, isOwnWallet: Bool, visualGram: Bool) {\n        self.visualGram = visualGram')
    replace(receive, '        if lhs.isOwnWallet != rhs.isOwnWallet {', '        if lhs.isOwnWallet != rhs.isOwnWallet || lhs.visualGram != rhs.visualGram {', expected=2)
    replace(receive, 'public init(context: AccountContext, address: String, isOwnWallet: Bool = true, appeared: (() -> Void)? = nil) {', 'public init(context: AccountContext, address: String, isOwnWallet: Bool = true, appeared: (() -> Void)? = nil, visualGram: Bool = false) {')
    replace(receive, 'component: WalletReceiveSheetComponent(context: context, address: address, isOwnWallet: isOwnWallet),', 'component: WalletReceiveSheetComponent(context: context, address: address, isOwnWallet: isOwnWallet, visualGram: visualGram),')
    replace(receive, '                        isPurchaseInProgress: componentState.isPurchaseInProgress,', '                        visualGram: context.component.visualGram,\n                        isPurchaseInProgress: componentState.isPurchaseInProgress,')
    replace(receive, '                        buy: { [weak componentState] in\n                            guard isOwnWallet else { return }', '                        buy: { [weak componentState, visualGram = context.component.visualGram] in\n                            guard isOwnWallet && !visualGram else { return }')
    replace(receive, """                        component: AnyComponent(WalletReceiveQrComponent(
                            address: component.address,""", r"""                        component: AnyComponent(WalletReceiveQrComponent(
                            address: component.visualGram ? component.address : "ton://transfer/\(component.address)",""")
    replace(receive, r'                        string: "ton://transfer/\(component.address)",', '                        string: component.address,')

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
    replace(entries, '    associatedData: ChatMessageItemAssociatedData,\n', '    associatedData: ChatMessageItemAssociatedData,\n    visualGramPeer: EnginePeer?,\n')
    replace(entries, '    if subject == nil, case let .peer(peerId) = location, let chatPeer, chatPeer.id == peerId {', '''    if includeEmptyEntry, subject == nil, case let .peer(peerId) = location,
       let localPeer = visualGramPeer ?? chatPeer.flatMap(EnginePeer.init), localPeer.id == peerId {''')
    replace(entries, '            peer: EnginePeer(chatPeer),\n            accountPeer: accountPeer,', '            peer: localPeer,\n            accountPeer: accountPeer,')
    replace(entries, '        if !messages.isEmpty {\n            entries.append(contentsOf: messages.map {', '        if !messages.isEmpty {\n            if view.entries.isEmpty {\n                entries.removeAll { entry in\n                    if case .ChatInfoEntry = entry { return true }\n                    return false\n                }\n            }\n            entries.append(contentsOf: messages.map {')

    history = ui / "Sources/ChatHistoryListNode.swift"
    replace(history, '        let accountCountry: Signal<String?, NoError>\n', '''        let visualGramChatPeer: Signal<EnginePeer?, NoError>
        if subject == nil, tag == nil, mode == .bubbles, case let .peer(peerId) = chatLocation,
           peerId.namespace == Namespaces.Peer.CloudUser {
            visualGramChatPeer = context.engine.data.subscribe(TelegramEngine.EngineData.Item.Peer.Peer(id: peerId))
            |> distinctUntilChanged
        } else {
            visualGramChatPeer = .single(nil)
        }
        let accountAndChatPeer = combineLatest(accountPeer, visualGramChatPeer)

        let accountCountry: Signal<String?, NoError>
''')
    replace(history, '            accountPeer |> debug_measureTimeToFirstEvent(label: "chatHistoryNode_accountPeer"),', '            accountAndChatPeer |> debug_measureTimeToFirstEvent(label: "chatHistoryNode_accountPeer"),')
    replace(history, 'defaultReaction, accountPeer, accountCountry, suggestAudioTranscription, promises, topicAuthorId, translationState, maxReadStoryId, recommendedChannels, audioTranscriptionTrial, chatThemes, deviceContactsNumbers, contentSettings in\n', 'defaultReaction, accountAndChatPeer, accountCountry, suggestAudioTranscription, promises, topicAuthorId, translationState, maxReadStoryId, recommendedChannels, audioTranscriptionTrial, chatThemes, deviceContactsNumbers, contentSettings in\n            let (accountPeer, visualGramPeer) = accountAndChatPeer\n')
    replace(history, '                    associatedData: associatedData,\n                    updatingMedia: updatingMedia,', '                    associatedData: associatedData,\n                    visualGramPeer: visualGramPeer,\n                    updatingMedia: updatingMedia,')
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

    list_node = preview.with_name("ChatListNode.swift")
    replace(list_node, '        let chatListNodeViewTransition = combineLatest(queue: viewProcessingQueue,\n', '''        let localPreviews: Signal<[EnginePeer.Id: VisualGramChatListPreview], NoError>
        if case .chatList = mode, case .chatList = location {
            localPreviews = VisualGramLocalAppearance.shared.changes
            |> mapToSignal { _ -> Signal<[EnginePeer.Id: VisualGramChatListPreview], NoError> in
                let ids = visualGramChatPreviewPeerIds(accountId: accountPeerId)
                guard !ids.isEmpty else { return .single([:]) }
                return context.engine.data.subscribe(
                    EngineDataMap(ids.map(TelegramEngine.EngineData.Item.Peer.Peer.init)),
                    EngineDataMap(ids.map(TelegramEngine.EngineData.Item.Messages.ChatListIndex.init)),
                    EngineDataMap(ids.map(TelegramEngine.EngineData.Item.Messages.ChatListGroup.init)),
                    TelegramEngine.EngineData.Item.Peer.Peer(id: accountPeerId)
                )
                |> map { peers, indices, groups, accountPeer in
                    let now = Int32(clamping: Int64(Date().timeIntervalSince1970))
                    var result: [EnginePeer.Id: VisualGramChatListPreview] = [:]
                    for (id, peer) in peers {
                        guard let peer, let message = visualGramChatGiftMessages(
                            accountPeerId: accountPeerId, peer: peer, accountPeer: accountPeer,
                            fromTimestamp: nil, throughTimestamp: now
                        ).max(by: { $0.index < $1.index }) else { continue }
                        result[id] = VisualGramChatListPreview(peer: peer, message: message,
                            hasChatListIndex: (indices[id] ?? nil) != nil, group: groups[id] ?? nil)
                    }
                    return result
                }
            }
        } else {
            localPreviews = .single([:])
        }
        let chatListAndPreviews = combineLatest(chatListViewUpdate, localPreviews)
        let chatListNodeViewTransition = combineLatest(queue: viewProcessingQueue,
''')
    replace(list_node, '            chatListViewUpdate,\n            self.statePromise.get(),', '            chatListAndPreviews,\n            self.statePromise.get(),')
    replace(list_node, 'contacts, chatListFilters, accountIsPremiumAndPeer: ChatListNodeAccountPeerState) -> Signal<ChatListNodeListViewTransition, NoError> in\n            let (update, filter) = updateAndFilter', 'contacts, chatListFilters, accountIsPremiumAndPeer: ChatListNodeAccountPeerState) -> Signal<ChatListNodeListViewTransition, NoError> in\n            let ((update, filter), localPreviews) = updateAndFilter')
    replace(list_node, 'accountPeerId: accountPeerId, isMainTab: innerIsMainTab)\n', 'accountPeerId: accountPeerId, isMainTab: innerIsMainTab, localPreviews: localPreviews, includeLocalOnlyChats: (filter == nil || filter == .allChats) && location == .chatList(groupId: .root) && !isSideList)\n')

    list_entries = preview.with_name("ChatListNodeEntries.swift")
    replace(list_entries, 'func chatListNodeEntriesForView(', '''struct VisualGramChatListPreview {
    let peer: EnginePeer
    let message: EngineMessage
    let hasChatListIndex: Bool
    let group: EngineChatList.Group?
}

func chatListNodeEntriesForView(''')
    replace(list_entries, 'accountPeerId: EnginePeer.Id, isMainTab: Bool) -> (entries:', 'accountPeerId: EnginePeer.Id, isMainTab: Bool, localPreviews: [EnginePeer.Id: VisualGramChatListPreview], includeLocalOnlyChats: Bool) -> (entries:')
    replace(list_entries, '    var hasContacts = false\n', '''    var visibleLocalOnlyChats: [VisualGramChatListPreview] = []
    if includeLocalOnlyChats {
        let existing = Set(view.items.map { $0.renderedPeer.peerId } + view.additionalItems.map { $0.item.renderedPeer.peerId })
        let unpinned = view.items.compactMap { item -> EngineChatList.Item.Index? in
            guard case let .chatList(index) = item.index, index.pinningIndex == nil else { return nil }
            return item.index
        }
        let lowerBound = view.hasEarlier ? unpinned.first : nil
        let upperBound = view.hasLater ? unpinned.last : nil
        for (id, preview) in localPreviews {
            let index = EngineChatList.Item.Index.chatList(.init(pinningIndex: nil, messageIndex: preview.message.index))
            let itemId = ChatListNodeState.ItemId(peerId: id, threadId: nil)
            guard !existing.contains(id), !preview.hasChatListIndex, preview.group != .archive,
                  lowerBound.map({ $0 <= index }) ?? !view.hasEarlier,
                  upperBound.map({ index <= $0 }) ?? !view.hasLater,
                  !state.pendingRemovalItemIds.contains(itemId), !state.pendingClearHistoryPeerIds.contains(itemId) else { continue }
            visibleLocalOnlyChats.append(preview)
        }
    }

    var hasContacts = false
''')
    replace(list_entries, '        for contact in contacts {\n', '        existingPeerIds.formUnion(visibleLocalOnlyChats.map { $0.peer.id })\n        for contact in contacts {\n')
    replace(list_entries, 'displayHide: !view.items.isEmpty))', 'displayHide: !view.items.isEmpty || !visibleLocalOnlyChats.isEmpty))')
    replace(list_entries, '    var hasPinned = false\n', '    var hasPinned = false\n    var needsLocalSort = !visibleLocalOnlyChats.isEmpty\n')
    replace(list_entries, '        var draftState: ChatListItemContent.DraftState?\n        if let draft = entry.draft {', '''        var displayIndex = entry.index
        if case .chatList = mode, case .chatList = chatListLocation, case let .chatList(originalIndex) = entry.index,
           let peerId, !state.pendingClearHistoryPeerIds.contains(.init(peerId: peerId, threadId: threadId)),
           let preview = localPreviews[peerId],
           updatedMessages.last.map({ $0.timestamp <= preview.message.timestamp }) ?? true {
            updatedMessages = [preview.message]
            if originalIndex.pinningIndex == nil, preview.message.timestamp >= originalIndex.messageIndex.timestamp {
                displayIndex = .chatList(.init(pinningIndex: nil, messageIndex: preview.message.index))
                needsLocalSort = true
            }
        }

        var draftState: ChatListItemContent.DraftState?
        if let draft = entry.draft {''')
    replace(list_entries, '            index: offsetPinnedIndex(entry.index, offset: pinnedIndexOffset),', '            index: offsetPinnedIndex(displayIndex, offset: pinnedIndexOffset),')
    replace(list_entries, '    if let hiddenGeneralThread {\n', '''    for preview in visibleLocalOnlyChats {
        let id = preview.peer.id
        result.append(.PeerEntry(.init(
            index: .chatList(.init(pinningIndex: nil, messageIndex: preview.message.index)),
            presentationData: state.presentationData, messages: [preview.message], readState: nil,
            isRemovedFromTotalUnreadCount: false, draftState: nil, mediaDraftContentType: nil,
            peer: EngineRenderedPeer(peerId: id, peers: [id: preview.peer], associatedMedia: [:]), threadInfo: nil,
            presence: nil, hasUnseenMentions: false, hasUnseenReactions: false, hasUnseenPollVotes: false,
            editing: state.editing, hasActiveRevealControls: state.peerIdWithRevealedOptions == .init(peerId: id, threadId: nil),
            selected: state.selectedPeerIds.contains(id),
            inputActivities: state.peerInputActivities?.activities[.init(peerId: id, threadId: nil)],
            promoInfo: nil, hasFailedMessages: false, isContact: false, autoremoveTimeout: nil,
            forumTopicData: nil, topForumTopicItems: [], revealed: false, storyState: nil,
            requiresPremiumForMessaging: false, displayAsTopicList: false
        )))
    }
    if needsLocalSort {
        result.sort()
    }
    if let hiddenGeneralThread {
''')

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
