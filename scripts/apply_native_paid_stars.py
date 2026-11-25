"""Wire visual Stars statistics and local-only paid actions into Telegram 13.2."""
import shutil
from prepare_native import replace


def apply_paid_stars(root, project):
    core = root / "submodules/TelegramCore/Sources"
    ui = root / "submodules/TelegramUI"
    stars = ui / "Components/Stars/StarsTransactionsScreen/Sources"
    shutil.copyfile(project / "native/VisualGramPaidStars.swift", core / "VisualGramPaidStars.swift")
    shutil.copyfile(project / "native/VisualGramStarsStatisticsScreen.swift", stars / "VisualGramStarsStatisticsScreen.swift")

    transactions = stars / "StarsTransactionsScreen.swift"
    replace(transactions, '''    private let starsRevenueStatsContext: StarsRevenueStatsContext
''', '''    private let starsRevenueStatsContext: StarsRevenueStatsContext

    @objc private func openStarsStatistics() {
        if VisualGramLocalAppearance.shared.visualStarsBalance(accountId: self.context.account.peerId) != nil {
            self.push(visualGramStarsStatisticsScreen(context: self.context))
        } else {
            self.push(self.context.sharedContext.makeStarsStatisticsScreen(context: self.context, peerId: self.context.account.peerId, revenueContext: self.starsRevenueStatsContext))
        }
    }
''')
    replace(transactions, '''            } else {
                let controller = self.context.sharedContext.makeStarsStatisticsScreen(context: context, peerId: context.account.peerId, revenueContext: self.starsRevenueStatsContext)
                self.push(controller)
            }
        }
''', '''            } else {
                self.openStarsStatistics()
            }
        }
''')
    replace(transactions, '''        openTransactionImpl = { [weak self] transaction in
''', '''        if !starsContext.ton {
            self.navigationItem.rightBarButtonItem = UIBarButtonItem(title: "Статистика", style: .plain, target: self, action: #selector(self.openStarsStatistics))
        }

        openTransactionImpl = { [weak self] transaction in
''')

    composer = ui / "Sources/ChatControllerNode.swift"
    replace(composer, '''                    self.maybeSendEphemeralMessage { [weak self] in
                        guard let self else {
''', '''                    self.maybeSendEphemeralMessage { [weak self, weak controller] in
                        guard let self, let controller else {
''')
    replace(composer, '''                            controller.presentPaidMessageAlertIfNeeded(count: count, completion: { [weak self] postpone in
                                self?.sendCurrentMessage(postpone: postpone)
                            })
''', '''                            let sendWithTelegram: () -> Void = { [weak self, weak telegramController = controller] in
                                telegramController?.presentPaidMessageAlertIfNeeded(count: count, completion: { [weak self] postpone in
                                    self?.sendCurrentMessage(postpone: postpone)
                                })
                            }
                            if !self.presentVisualGramPaidMessageChoice(sendWithTelegram: sendWithTelegram) {
                                sendWithTelegram()
                            }
''')
    replace(composer, '''    func sendCurrentMessage(silentPosting: Bool? = nil,''', r'''    private func presentVisualGramPaidMessageChoice(sendWithTelegram: @escaping () -> Void) -> Bool {
        let store = VisualGramLocalAppearance.shared
        let accountId = self.context.account.peerId
        let state = self.chatPresentationInterfaceState
        guard let balance = store.visualStarsBalance(accountId: accountId),
              state.subject == nil, case let .peer(peerId) = state.chatLocation,
              peerId.namespace == Namespaces.Peer.CloudUser, peerId != accountId,
              state.interfaceState.editMessage == nil, state.interfaceState.forwardMessageIds?.isEmpty != false,
              state.interfaceState.replyMessageSubject == nil, state.interfaceState.postSuggestionState == nil,
              let price = state.sendPaidMessageStars?.value, price > 0,
              canSendMessagesToChat(state),
              let controller = self.controller, let panel = self.textInputPanelNode else { return false }

        let draft = panel.inputTextState
        guard draft.content.isEntityExpressible(options: []) else { return false }
        let text = expandedInputStateAttributedString(draft.inputText)
        let pieces = chatComposerTextMessages(effectiveInputText: text, businessLinkSetup: false).pieces.map { ($0.0.string, $0.1) }
        guard !pieces.isEmpty else { return false }
        let (total, overflow) = price.multipliedReportingOverflow(by: Int64(pieces.count))
        guard !overflow else { return false }

        let draftIsCurrent: () -> Bool = { [weak self, weak panel] in
            guard let self, let panel else { return false }
            let current = self.chatPresentationInterfaceState
            return current.chatLocation.peerId == peerId
                && current.sendPaidMessageStars?.value == price
                && current.interfaceState.editMessage == nil
                && current.interfaceState.forwardMessageIds?.isEmpty != false
                && current.interfaceState.replyMessageSubject == nil
                && current.interfaceState.postSuggestionState == nil
                && canSendMessagesToChat(current)
                && panel.inputTextState.inputText.isEqual(to: draft.inputText)
        }
        let alert = textAlertController(context: self.context, title: "Платное сообщение",
            text: "Визуальный баланс: \(balance) ⭐. Визуальное сообщение останется на этом устройстве.",
            actions: [
                TextAlertAction(type: .defaultAction, title: "Визуально за \(total) ⭐", action: { [weak self, weak controller, weak panel] in
                    guard let self, let controller, let panel, draftIsCurrent() else { return }
                    let now = Int32(clamping: Int64(Date().timeIntervalSince1970))
                    let result = store.sendVisualPaidMessages(accountId: accountId, peerId: peerId, messages: pieces, price: price, now: now)
                    guard result == .saved else {
                        controller.showVisualGramStarsSpendError(result)
                        return
                    }
                    self.updateTypingActivity(false)
                    panel.text = ""
                    self.requestUpdateChatInterfaceState(.immediate, true, {
                        $0.withUpdatedComposeInputState(ChatTextInputState(inputText: NSAttributedString(string: "")))
                            .withUpdatedComposeDisableUrlPreviews([])
                            .withUpdatedSendMessageEffect(nil)
                    })
                    self.historyNode.scrollToEndOfHistory()
                }),
                TextAlertAction(type: .genericAction, title: "Отправить в Telegram", action: {
                    if draftIsCurrent() { sendWithTelegram() }
                }),
                TextAlertAction(type: .genericAction, title: controller.presentationData.strings.Common_Cancel, action: {})
            ], actionLayout: .vertical)
        controller.present(alert, in: .window(.root))
        return true
    }

    func sendCurrentMessage(silentPosting: Bool? = nil,''')

    history = ui / "Sources/ChatHistoryEntriesForView.swift"
    replace(history, '''    loop: for entry in view.entries {
        var message = entry.message.withAppliedEphemeralReplacementMessage()
''', '''    let visualPaidReactions: [String: Int32]
    if subject == nil, case let .peer(peerId) = location, peerId.namespace == Namespaces.Peer.CloudChannel {
        visualPaidReactions = VisualGramLocalAppearance.shared.visualPaidReactions(accountId: context.account.peerId)
    } else {
        visualPaidReactions = [:]
    }
    loop: for entry in view.entries {
        var message = entry.message.withAppliedEphemeralReplacementMessage()
        if !visualPaidReactions.isEmpty, let count = visualPaidReactions[VisualGramLocalAppearance.visualPaidReactionKey(message.id)] {
            message = VisualGramLocalAppearance.displayingVisualPaidReaction(message, count: count)
        }
''')

    context_menu = ui / "Sources/Chat/ChatControllerOpenMessageContextMenu.swift"
    replace(context_menu, 'import ReactionSelectionNode\n', 'import ReactionSelectionNode\nimport ChatSendStarsScreen\n')
    replace(context_menu, '''extension ChatControllerImpl {
''', r'''extension ChatControllerImpl {
    func showVisualGramStarsSpendError(_ result: VisualGramStarsSpendResult) {
        let text = result == .insufficientBalance ? "Недостаточно визуальных звёзд." : "Операцию не удалось сохранить."
        self.present(textAlertController(context: self.context, title: nil, text: text, actions: [
            TextAlertAction(type: .defaultAction, title: self.presentationData.strings.Common_OK, action: {})
        ]), in: .window(.root))
    }

    func presentVisualGramPaidReaction(messageId: EngineMessage.Id) {
        guard canSendReactionsToChat(self.presentationInterfaceState),
              let channel = self.presentationInterfaceState.renderedPeer?.chatMainPeer as? TelegramChannel,
              case .broadcast = channel.info, messageId.peerId == channel.id,
              messageId.namespace == Namespaces.Message.Cloud else { return }
        guard VisualGramLocalAppearance.shared.visualStarsBalance(accountId: self.context.account.peerId) != nil else { return }
        let _ = (self.context.engine.data.get(TelegramEngine.EngineData.Item.Messages.Message(id: messageId))
        |> deliverOnMainQueue).startStandalone(next: { [weak self] message in
            guard let self, let message, message.adAttribute == nil else { return }
            let store = VisualGramLocalAppearance.shared
            let peers = store.visualReactionTopPeers(accountId: self.context.account.peerId, messageId: messageId,
                existing: mergedMessageReactions(attributes: message.attributes, isTags: false)?.topPeers ?? [])
            let _ = (ChatSendStarsScreen.initialData(context: self.context, peerId: messageId.peerId, reactSubject: .message(messageId),
                topPeers: peers, visualReactionId: messageId, completion: { _, _, _, _ in })
            |> deliverOnMainQueue).startStandalone(next: { [weak self] data in
                guard let self, let data else { return }
                self.push(ChatSendStarsScreen(context: self.context, initialData: data))
            })
        })
    }

''')
    replace(context_menu, '''                case let .list(itemList):
                    if itemList.isEmpty {
                        return
                    }
                case .custom, .twoLists:
''', '''                case let .list(itemList):
                    if allowedReactionsAndStars.areStarsEnabled, let channel = self.presentationInterfaceState.renderedPeer?.chatMainPeer as? TelegramChannel,
                       case .broadcast = channel.info, message.id.peerId == channel.id, message.id.namespace == Namespaces.Message.Cloud,
                       message.adAttribute == nil, canSendReactionsToChat(self.presentationInterfaceState),
                       VisualGramLocalAppearance.shared.visualStarsBalance(accountId: self.context.account.peerId) != nil {
                        let action = ContextMenuActionItem(text: "Визуальные звёзды", icon: { theme in
                            generateTintedImage(image: UIImage(systemName: "star.fill"), color: theme.contextMenu.primaryColor)
                        }, action: { [weak self] _, complete in
                            complete(.default)
                            self?.presentVisualGramPaidReaction(messageId: message.id)
                        })
                        actions.content = .list([.action(action), .separator] + itemList)
                    } else if itemList.isEmpty {
                        return
                    }
                case .custom, .twoLists:
''')
    replace(context_menu, '''            let title = isGramTransfer ? self.presentationData.strings.Conversation_ContextMenuDelete : "Удалить подарок из чата?"
            let text = isGramTransfer ? "" : "Карточка исчезнет из переписки. Подарок останется в профиле владельца."
''', '''            let isVisualMessage = message.media.isEmpty
            if isVisualMessage {
                actions.removeAll()
                actions.append(TextAlertAction(type: .destructiveAction, title: "Удалить", action: { remove(false) }))
                actions.append(TextAlertAction(type: .genericAction, title: self.presentationData.strings.Common_Cancel, action: {}))
            }
            let title = isGramTransfer || isVisualMessage ? self.presentationData.strings.Conversation_ContextMenuDelete : "Удалить подарок из чата?"
            let text = isGramTransfer || isVisualMessage ? "" : "Карточка исчезнет из переписки. Подарок останется в профиле владельца."
''')

    chat = ui / "Sources/ChatController.swift"
    replace(chat, '''                    if case .stars = chosenReaction {
                        if !canSendReactionsToChat(strongSelf.presentationInterfaceState) {
''', '''                    if case .stars = chosenReaction {
                        if VisualGramLocalAppearance.shared.visualStarsBalance(accountId: strongSelf.context.account.peerId) != nil {
                            strongSelf.presentVisualGramPaidReaction(messageId: message.id)
                            return
                        }
                        if !canSendReactionsToChat(strongSelf.presentationInterfaceState) {
''')


    replace(context_menu, '''                    if case .stars = chosenUpdatedReaction.reaction {
''', '''                    if case .stars = chosenUpdatedReaction.reaction {
                        if VisualGramLocalAppearance.shared.visualStarsBalance(accountId: self.context.account.peerId) != nil {
                            controller?.dismiss(completion: { [weak self] in
                                self?.presentVisualGramPaidReaction(messageId: message.id)
                            })
                            return
                        }
''')
    reaction_menu = ui / "Sources/ChatControllerOpenMessageReactionContextMenu.swift"
    replace(reaction_menu, '    func openMessageSendStarsScreen(message: EngineMessage) {\n', '''    func openMessageSendStarsScreen(message: EngineMessage) {
        if VisualGramLocalAppearance.shared.visualStarsBalance(accountId: self.context.account.peerId) != nil {
            self.presentVisualGramPaidReaction(messageId: message.id)
            return
        }
''')
    apply_native_reaction_screen(root)


def apply_native_reaction_screen(root):
    screen = root / "submodules/TelegramUI/Components/Chat/ChatSendStarsScreen/Sources/ChatSendStarsScreen.swift"
    replace(screen, 'import StoryLiveChatMessageComponent\n', 'import StoryLiveChatMessageComponent\nimport PresentationDataUtils\n')
    replace(screen.parents[1] / "BUILD", '        "//submodules/Display",\n', '        "//submodules/Display",\n        "//submodules/PresentationDataUtils",\n')
    replace(screen, '''        fileprivate let balance: StarsAmount?
''', '''        fileprivate let balance: StarsAmount?
        fileprivate let visualReactionId: EngineMessage.Id?
''')
    replace(screen, '''            balance: StarsAmount?
        ) {
            self.subjectInitialData = subjectInitialData
            self.balance = balance
''', '''            balance: StarsAmount?,
            visualReactionId: EngineMessage.Id? = nil
        ) {
            self.subjectInitialData = subjectInitialData
            self.balance = balance
            self.visualReactionId = visualReactionId
''')
    replace(screen, 'topPeers: [ReactionsMessageAttribute.TopPeer], completion:', 'topPeers: [ReactionsMessageAttribute.TopPeer], visualReactionId: EngineMessage.Id? = nil, completion:')
    replace(screen, '''public static func initialData(context: AccountContext, peerId: EnginePeer.Id, myPeer: EnginePeer? = nil, reactSubject: ReactSubject, topPeers: [ReactionsMessageAttribute.TopPeer], visualReactionId: EngineMessage.Id? = nil, completion: @escaping (Int64, TelegramPaidReactionPrivacy, Bool, TransitionOut) -> Void) -> Signal<InitialData?, NoError> {
        let balance: Signal<StarsAmount?, NoError>
        if let starsContext = context.starsContext {
''', '''public static func initialData(context: AccountContext, peerId: EnginePeer.Id, myPeer: EnginePeer? = nil, reactSubject: ReactSubject, topPeers: [ReactionsMessageAttribute.TopPeer], visualReactionId: EngineMessage.Id? = nil, completion: @escaping (Int64, TelegramPaidReactionPrivacy, Bool, TransitionOut) -> Void) -> Signal<InitialData?, NoError> {
        let balance: Signal<StarsAmount?, NoError>
        if visualReactionId != nil {
            balance = .single(StarsAmount(value: VisualGramLocalAppearance.shared.visualStarsBalance(accountId: context.account.peerId) ?? 0, nanos: 0))
        } else if let starsContext = context.starsContext {
''', expected=1)
    # The second factory is for livestream messages and has the same balance code.
    replace(screen, '''                balance: balance
            )
        }
    }
    
    public static func initialDataLiveStreamMessage''', '''                balance: balance,
                visualReactionId: visualReactionId
            )
        }
    }
    
    public static func initialDataLiveStreamMessage''')
    replace(screen, '''                if let starsContext = component.context.starsContext {
                    self.balanceDisposable = (starsContext.state
''', '''                if component.initialData.visualReactionId != nil {
                    self.balanceDisposable = (VisualGramLocalAppearance.shared.changes
                    |> deliverOnMainQueue).startStrict(next: { [weak self] _ in
                        guard let self else { return }
                        self.balance = StarsAmount(value: VisualGramLocalAppearance.shared.visualStarsBalance(accountId: component.context.account.peerId) ?? 0, nanos: 0)
                        if !self.isUpdating { self.state?.updated(transition: .immediate) }
                    })
                } else if let starsContext = component.context.starsContext {
                    self.balanceDisposable = (starsContext.state
''')
    # Both identity controls must stay inside the visual ledger.
    for indent in ['                                ', '                                        ']:
        old = indent + 'let _ = component.context.engine.messages.updateStarsReactionPrivacy(id: messageId, privacy: mappedPrivacy).startStandalone()'
        new = indent + '''if component.initialData.visualReactionId != nil {
''' + indent + '''    VisualGramLocalAppearance.shared.setVisualReactionPrivacy(accountId: component.context.account.peerId, messageId: messageId, privacy: mappedPrivacy)
''' + indent + '''} else {
''' + indent + '''    let _ = component.context.engine.messages.updateStarsReactionPrivacy(id: messageId, privacy: mappedPrivacy).startStandalone()
''' + indent + '''}'''
        # Match indentation at the beginning of a line.
        replace(screen, '\n' + old + '\n', '\n' + new + '\n')
    replace(screen, '''                            action: { [weak self] in
                                guard let self, let component = self.component, let starsContext = context.starsContext,''', '''                            action: { [weak self] in
                                if self?.component?.initialData.visualReactionId != nil { return }
                                guard let self, let component = self.component, let starsContext = context.starsContext,''')
    replace(screen, '''                        if balance < StarsAmount(value: Int64(self.amount.realValue), nanos: 0) {
''', '''                        if component.initialData.visualReactionId != nil && balance < StarsAmount(value: Int64(self.amount.realValue), nanos: 0) {
                            self.presentVisualStarsError(.insufficientBalance, component: component)
                            return
                        }
                        if balance < StarsAmount(value: Int64(self.amount.realValue), nanos: 0) {
''')
    replace(screen, '''                        switch component.initialData.subjectInitialData {
                        case let .react(reactData):
                            reactData.completion(
''', '''                        if let messageId = component.initialData.visualReactionId {
                            guard !self.didCommitVisualReaction else { return }
                            let result = VisualGramLocalAppearance.shared.addVisualPaidReaction(
                                accountId: component.context.account.peerId, messageId: messageId,
                                count: Int32(clamping: self.amount.realValue), privacy: mappedPrivacy,
                                now: Int32(clamping: Int64(Date().timeIntervalSince1970)))
                            guard result == .saved else {
                                self.presentVisualStarsError(result, component: component)
                                return
                            }
                            self.didCommitVisualReaction = true
                            self.environment?.controller()?.dismiss()
                            return
                        }
                        switch component.initialData.subjectInitialData {
                        case let .react(reactData):
                            reactData.completion(
''')
    replace(screen, '''        private var balanceDisposable: Disposable?
''', '''        private var balanceDisposable: Disposable?
        private var didCommitVisualReaction = false

        private func presentVisualStarsError(_ result: VisualGramStarsSpendResult, component: ChatSendStarsScreenComponent) {
            let presentationData = component.context.sharedContext.currentPresentationData.with { $0 }
            let text = result == .insufficientBalance ? "Недостаточно визуальных звёзд." : "Операцию не удалось сохранить."
            let controller = standardTextAlertController(theme: AlertControllerTheme(presentationData: presentationData),
                title: nil, text: text, actions: [TextAlertAction(type: .defaultAction, title: presentationData.strings.Common_OK, action: {})])
            self.environment?.controller()?.present(controller, in: .window(.root))
        }
''')

