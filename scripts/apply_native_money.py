"""Route DuckGram's local GRAM balance through the Telegram wallet entry points."""
import shutil

from prepare_native import replace


def apply_money(root, project):
    ui = root / "submodules/TelegramUI"
    wallet_send = ui / "Components/Wallet/WalletSendScreen"
    shutil.copyfile(project / "native/VisualGramMoneyScreen.swift", wallet_send / "Sources/VisualGramMoneyScreen.swift")
    replace(wallet_send / "BUILD", '        "//submodules/AccountContext",\n', '''        "//submodules/AccountContext",
        "//submodules/AsyncDisplayKit",
        "//submodules/TelegramUI/Components/Wallet/WalletCardComponent",
        "//submodules/TelegramUI/Components/Wallet/WalletGiftStickerMediaComponent",
''')

    attachment = ui / "Sources/ChatControllerOpenAttachmentMenu.swift"
    replace(attachment, '            switch subject {\n            case .default, .gift:\n                if WalletConfiguration', '''            let hasLocalMoney = VisualGramLocalAppearance.shared.localGramBalance(accountId: self.context.account.peerId) != nil
            switch subject {
            case .default, .gift:
                if (hasLocalMoney || WalletConfiguration''')
    replace(attachment, ').isAvailable, !isScheduledMessages, banSendText', ').isAvailable), !isScheduledMessages, banSendText')
    replace(attachment, '                        guard let walletContext = strongSelf.context.walletContext else {\n', '''                        if hasLocalMoney {
                            let controller = VisualGramSendMoneyScreen(context: strongSelf.context, peer: peer, dismissAttachment: { [weak attachmentController] in
                                attachmentController?.dismiss(animated: true)
                            }, completed: { [weak self] in
                                self?.scrollToEndOfHistory()
                            })
                            completion(controller, controller.mediaPickerContext)
                            strongSelf.controllerNavigationDisposable.set(nil)
                            return true
                        }
                        guard let walletContext = strongSelf.context.walletContext else {
''')

    peer_info = ui / "Components/PeerInfo/PeerInfoScreen/Sources"
    menu = peer_info / "PeerInfoScreenPerformButtonAction.swift"
    replace(menu, '                    if WalletConfiguration.with(appConfiguration: strongSelf.context.currentAppConfiguration.with { $0 }).isAvailable, strongSelf.peerId.namespace', '''                    let hasLocalMoney = VisualGramLocalAppearance.shared.localGramBalance(accountId: strongSelf.context.account.peerId) != nil
                    if (hasLocalMoney || WalletConfiguration.with(appConfiguration: strongSelf.context.currentAppConfiguration.with { $0 }).isAvailable), strongSelf.peerId.namespace''')
    replace(menu, '''                            guard let self, let controller = self.controller, let peer = self.data?.peer, let walletContext = self.context.walletContext else {
                                return
                            }
                            let sendController = WalletSendScreen''', '''                            guard let self, let controller = self.controller, let peer = self.data?.peer else { return }
                            if hasLocalMoney {
                                controller.push(VisualGramSendMoneyScreen(context: self.context, peer: peer, completed: { [weak self] in
                                    self?.openVisualGramMoneyChat(peer)
                                }))
                                return
                            }
                            guard let walletContext = self.context.walletContext else { return }
                            let sendController = WalletSendScreen''')

    profile = peer_info / "PeerInfoScreen.swift"
    replace(profile, '                if peer.id == self.context.account.peerId {\n                    guard WalletConfiguration', '''                let accountId = self.context.account.peerId
                let store = VisualGramLocalAppearance.shared
                let hasLocalMoney = store.localGramBalance(accountId: accountId) != nil
                if peer.id == accountId {
                    if hasLocalMoney {
                        peerWalletScreen.openScreen(VisualGramMoneyScreen(context: self.context))
                        return
                    }
                    guard WalletConfiguration''')
    replace(profile, '''                let localWallet = VisualGramLocalAppearance.shared.appearance(accountId: self.context.account.peerId, targetPeerId: peer.id)
                if localWallet.enabled && localWallet.grams != nil { return }
''', '''                let recipientWallet = store.appearance(accountId: accountId, targetPeerId: peer.id)
                if hasLocalMoney || (recipientWallet.enabled && recipientWallet.grams != nil) {
                    peerWalletScreen.openScreen(VisualGramSendMoneyScreen(context: self.context, peer: peer, completed: { [weak self] in
                        self?.openVisualGramMoneyChat(peer)
                    }))
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
                noticeString = "Локальный баланс DuckGram"
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
    replace(settings_action, 'import WalletContext\n', 'import WalletContext\nimport WalletSendScreen\n')
    replace(settings_action, '        case .wallet:\n', '''        case .wallet:
            if VisualGramLocalAppearance.shared.localGramBalance(accountId: self.context.account.peerId) != nil {
                push(VisualGramMoneyScreen(context: self.context))
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
    replace(transfer_bubble, '                let addressLayoutArguments = TextNodeLayoutArguments(\n', '''                let addressText = localTransfer ? "Локальный перевод DuckGram" : addressGroups.joined(separator: " ")
                let addressLayoutArguments = TextNodeLayoutArguments(
''')
    replace(transfer_bubble, 'string: addressGroups.joined(separator: " "),', 'string: addressText,', expected=2)
    chat = ui / "Sources/ChatController.swift"
    replace(chat, '                        case let .gramTransfer(amount, peerAddress, transactionId, messageComment, commentEncrypted):\n', '''                        case let .gramTransfer(amount, peerAddress, transactionId, messageComment, commentEncrypted):
                            if message.id.namespace == Int32.max - 42 {
                                let amountText = formatTonAmountText(amount, dateTimeFormat: self.presentationData.dateTimeFormat, maxDecimalPositions: 9, formatString: self.presentationData.strings.Currency_Grams)
                                let details = [amountText, messageComment].compactMap { $0 }.joined(separator: "\\n\\n")
                                self.present(textAlertController(context: self.context, title: "Локальный перевод DuckGram", text: details, actions: [TextAlertAction(type: .defaultAction, title: self.presentationData.strings.Common_OK, action: {})]), in: .window(.root))
                                return true
                            }
''')
    context_menu = ui / "Sources/Chat/ChatControllerOpenMessageContextMenu.swift"
    replace(context_menu, '            let alert = textAlertController(context: self.context, title: "Удалить подарок из чата?", text: "Карточка исчезнет из переписки. Подарок останется в профиле владельца.", actions: actions, actionLayout: .vertical)\n', '''            let isGramTransfer = message.media.contains { media in
                if let action = media as? TelegramMediaAction, case .gramTransfer = action.action { return true }
                return false
            }
            let title = isGramTransfer ? "Удалить перевод из чата?" : "Удалить подарок из чата?"
            let text = isGramTransfer ? "Карточка исчезнет из переписки. Перевод останется в истории баланса." : "Карточка исчезнет из переписки. Подарок останется в профиле владельца."
            let alert = textAlertController(context: self.context, title: title, text: text, actions: actions, actionLayout: .vertical)
''')

    preview = root / "submodules/ChatListUI/Sources/Node/ChatListItemStrings.swift"
    replace(preview, '                            case .gramTransfer where message.effectivelyIncoming(accountPeerId):\n', '''                            case let .gramTransfer(amount, _, _, _, _) where message.id.namespace == Int32.max - 42:
                                hideAuthor = true
                                richTextPreview = nil
                                let formatted = formatTonAmountText(amount, dateTimeFormat: dateTimeFormat, maxDecimalPositions: 9, formatString: strings.Currency_Grams)
                                messageText = "Локальный перевод: " + (message.flags.contains(.Incoming) ? "+" : "−") + formatted
                            case .gramTransfer where message.effectivelyIncoming(accountPeerId):
''')
    list_item = preview.with_name("ChatListItem.swift")
    replace(list_item, '                let hasUnreadIncomingGramTransfer = messages.last.map { message in\n',
            '                let hasUnreadIncomingGramTransfer = messages.last.map { message in\n                    guard message.id.namespace != Int32.max - 42 else { return false }\n')
