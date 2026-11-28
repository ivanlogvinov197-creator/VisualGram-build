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
    replace(composer, 'import TelegramCore\n', 'import TelegramCore\nimport ChatMessagePaymentAlertController\n')
    replace(composer, '''                    self.maybeSendEphemeralMessage { [weak self] in
                        guard let self else {
''', '''                    self.maybeSendEphemeralMessage { [weak self, weak controller] in
                        guard let self, let controller else {
''')
    replace(composer, '''                            controller.presentPaidMessageAlertIfNeeded(count: count, completion: { [weak self] postpone in
                                self?.sendCurrentMessage(postpone: postpone)
                            })
''', '''                            if !self.presentLocalPaidMessageConfirmation() {
                                controller.presentPaidMessageAlertIfNeeded(count: count, completion: { [weak self] postpone in
                                    self?.sendCurrentMessage(postpone: postpone)
                                })
                            }
''')
    replace(composer, '''    func sendCurrentMessage(silentPosting: Bool? = nil,''', r'''    private func presentLocalPaidMessageConfirmation() -> Bool {
        let store = VisualGramLocalAppearance.shared
        let accountId = self.context.account.peerId
        let state = self.chatPresentationInterfaceState
        guard store.visualStarsBalance(accountId: accountId) != nil,
              state.subject == nil, case let .peer(peerId) = state.chatLocation,
              peerId.namespace == Namespaces.Peer.CloudUser, peerId != accountId,
              state.interfaceState.editMessage == nil, state.interfaceState.forwardMessageIds?.isEmpty != false,
              state.interfaceState.replyMessageSubject == nil, state.interfaceState.postSuggestionState == nil,
              let price = state.sendPaidMessageStars?.value, price > 0,
              canSendMessagesToChat(state),
              let renderedPeer = state.renderedPeer.flatMap(EngineRenderedPeer.init),
              let controller = self.controller, let panel = self.textInputPanelNode else { return false }

        let draft = panel.inputTextState
        guard draft.content.isEntityExpressible(options: []) else { return false }
        let text = expandedInputStateAttributedString(draft.inputText)
        let pieces = chatComposerTextMessages(effectiveInputText: text, businessLinkSetup: false).pieces.map { ($0.0.string, $0.1) }
        guard !pieces.isEmpty else { return false }
        guard let count = Int32(exactly: pieces.count), !price.multipliedReportingOverflow(by: Int64(count)).overflow else {
            controller.showVisualGramStarsSpendError(.unavailable)
            return true
        }

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
        let consentKey = "DuckGram.PaidMessageConfirmation.\(accountId.toInt64()).\(peerId.toInt64())"
        var committed = false
        let commit: (Bool) -> Void = { [weak self, weak paymentController = controller, weak inputPanel = panel] remember in
            guard !committed, let self, let controller = paymentController, let panel = inputPanel, draftIsCurrent() else { return }
            committed = true
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
            if remember { UserDefaults.standard.set(NSNumber(value: price), forKey: consentKey) }
        }
        if (UserDefaults.standard.object(forKey: consentKey) as? NSNumber)?.int64Value == price {
            commit(false)
        } else {
            let alert = chatMessagePaymentAlertController(context: self.context,
                presentationData: controller.presentationData, updatedPresentationData: nil,
                peers: [renderedPeer], count: count, amount: StarsAmount(value: price, nanos: 0),
                totalAmount: nil, hasCheck: true, navigationController: controller.navigationController as? NavigationController,
                completion: commit)
            controller.present(alert, in: .window(.root))
        }
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
    replace(context_menu, '''extension ChatControllerImpl {
''', r'''extension ChatControllerImpl {
    func showVisualGramStarsSpendError(_ result: VisualGramStarsSpendResult) {
        let text = result == .insufficientBalance ? "Недостаточно звёзд." : "Операцию не удалось сохранить."
        self.present(textAlertController(context: self.context, title: nil, text: text, actions: [
            TextAlertAction(type: .defaultAction, title: self.presentationData.strings.Common_OK, action: {})
        ]), in: .window(.root))
    }

    func commitQuickLocalStar(_ message: EngineMessage, onFailure: @escaping () -> Void) {
        let store = VisualGramLocalAppearance.shared
        let accountId = self.context.account.peerId
        guard let channel = self.presentationInterfaceState.renderedPeer?.chatMainPeer as? TelegramChannel,
              case .broadcast = channel.info, message.id.peerId == channel.id, message.adAttribute == nil,
              message.id.namespace == Namespaces.Message.Cloud else {
            onFailure()
            return
        }
        let _ = (self.context.engine.data.get(TelegramEngine.EngineData.Item.Peer.ReactionSettings(id: channel.id))
        |> deliverOnMainQueue).startStandalone(next: { [weak self] settings in
            guard let self, self.chatLocation.peerId == channel.id else { return }
            if case let .known(value) = settings, value.starsAllowed == false {
                onFailure()
                self.displaySendReactionRestrictedToast()
                return
            }
            let privacy = store.visualReactionPrivacy(accountId: accountId, messageId: message.id)
            let result = store.addVisualPaidReaction(accountId: accountId, messageId: message.id,
                count: 1, privacy: privacy, now: Int32(clamping: Int64(Date().timeIntervalSince1970)))
            if result != .saved {
                onFailure()
                self.showVisualGramStarsSpendError(result)
            }
        })
    }

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
    chat_anchor = '''                        guard let starsContext = strongSelf.context.starsContext else {
                            return
                        }
                        guard let peerId = strongSelf.chatLocation.peerId else {
'''
    replace(chat, chat_anchor, '''                        if VisualGramLocalAppearance.shared.visualStarsBalance(accountId: strongSelf.context.account.peerId) != nil {
                            strongSelf.commitQuickLocalStar(EngineMessage(message), onFailure: { [weak itemNode] in
                                itemNode?.awaitingAppliedReaction = nil
                            })
                            return
                        }
''' + chat_anchor)
    context_anchor = '''                        guard let starsContext = self.context.starsContext else {
                            return
                        }
                        let _ = (combineLatest(
                            starsContext.state,
                            self.context.engine.data.get(TelegramEngine.EngineData.Item.Peer.ReactionSettings(id: message.id.peerId))
'''
    replace(context_menu, context_anchor, '''                        if VisualGramLocalAppearance.shared.visualStarsBalance(accountId: self.context.account.peerId) != nil {
                            self.commitQuickLocalStar(EngineMessage(message), onFailure: { [weak self, weak menuController = controller] in
                                self?.chatDisplayNode.historyNode.forEachItemNode { itemNode in
                                    guard let itemNode = itemNode as? ChatMessageItemView, itemNode.item?.message.id == message.id else { return }
                                    itemNode.awaitingAppliedReaction = nil
                                }
                                menuController?.dismiss()
                            })
                            return
                        }
''' + context_anchor)

    reaction_menu = ui / "Sources/ChatControllerOpenMessageReactionContextMenu.swift"
    replace(reaction_menu, '        self.context.engine.messages.forceSendPendingSendStarsReaction(id: message.id)\n', '''        let store = VisualGramLocalAppearance.shared
        let accountId = self.context.account.peerId
        let localStars = store.visualStarsBalance(accountId: accountId) != nil
        if localStars {
            guard let channel = self.presentationInterfaceState.renderedPeer?.chatMainPeer as? TelegramChannel,
                  case .broadcast = channel.info, channel.id == message.id.peerId, message.adAttribute == nil,
                  message.id.namespace == Namespaces.Message.Cloud else { return }
        } else {
            self.context.engine.messages.forceSendPendingSendStarsReaction(id: message.id)
        }
''')
    replace(reaction_menu, '''            let _ = (ChatSendStarsScreen.initialData(context: self.context, peerId: message.id.peerId, reactSubject: .message(message.id), topPeers: reactionsAttribute?.topPeers ?? [], completion:''', '''            let peers = reactionsAttribute?.topPeers ?? []
            if localStars, case let .known(settings) = reactionSettings, settings.starsAllowed == false {
                self.displaySendReactionRestrictedToast()
                return
            }
            let displayedPeers = localStars ? store.visualReactionTopPeers(accountId: accountId, messageId: message.id, existing: peers) : peers
            let _ = (ChatSendStarsScreen.initialData(context: self.context, peerId: message.id.peerId, reactSubject: .message(message.id), topPeers: displayedPeers, visualReactionId: localStars ? message.id : nil, completion:''')
    replace(reaction_menu, '                let _ = self.context.engine.messages.sendStarsReaction(id: message.id, count: Int(amount), privacy: privacy).startStandalone()\n', '''                if localStars { return }
                let _ = self.context.engine.messages.sendStarsReaction(id: message.id, count: Int(amount), privacy: privacy).startStandalone()
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
            let text = result == .insufficientBalance ? "Недостаточно звёзд." : "Операцию не удалось сохранить."
            let controller = standardTextAlertController(theme: AlertControllerTheme(presentationData: presentationData),
                title: nil, text: text, actions: [TextAlertAction(type: .defaultAction, title: presentationData.strings.Common_OK, action: {})])
            self.environment?.controller()?.present(controller, in: .window(.root))
        }
''')

