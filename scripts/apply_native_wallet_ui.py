from prepare_native import replace


def apply_wallet_send(wallet_send):
    source = wallet_send / "Sources/WalletSendScreen.swift"
    replace(source, "    let peer: EnginePeer?\n    let resolvedAddress:", "    let peer: EnginePeer?\n    let visualGram: Bool\n    let resolvedAddress:")
    replace(source, "        peer: EnginePeer?,\n        resolvedAddress:", "        peer: EnginePeer?,\n        visualGram: Bool = false,\n        resolvedAddress:")
    replace(source, "        self.peer = peer\n        self.resolvedAddress", "        self.peer = peer\n        self.visualGram = visualGram\n        self.resolvedAddress")
    replace(source, "        if lhs.peer != rhs.peer {", "        if lhs.peer != rhs.peer || lhs.visualGram != rhs.visualGram {")
    replace(source, "        private func resolvePeerAddressIfNeeded() {\n", "        private func resolvePeerAddressIfNeeded() {\n            guard self.component?.visualGram != true else { return }\n")
    replace(source, "            guard let walletAddress = self.walletAddress else {\n                return\n            }\n            let receiveController", """            if component.visualGram {
                let receive = component.context.sharedContext.makeWalletReceiveScreen(context: component.context, address: VisualGramLocalAppearance.visualWalletAddress(peerId: component.context.account.peerId))
                if let parent = (controller as? AttachmentContainable)?.parentController() {
                    parent.push(receive)
                } else {
                    controller.push(receive)
                }
                return
            }
            guard let walletAddress = self.walletAddress else {
                return
            }
            let receiveController""")
    replace(source, "                content: content,\n                actions: [\n                    AlertScreen.Action(title: strings.Common_Cancel),", """                content: component.visualGram ? Array(content.dropLast()) : content,
                actions: [
                    AlertScreen.Action(title: strings.Common_Cancel),""")
    replace(source, "        private func send() {\n", """        private func send() {
            if let component = self.component, component.visualGram {
                self.sendVisualGram(component: component)
                return
            }
""")
    replace(source, "        /// A send while transfers are faked", """        private func sendVisualGram(component: WalletSendScreenComponent) {
            guard let controller = self.environment?.controller() as? WalletSendScreen,
                  !self.recipientAddress.isEmpty, self.isVisible, self.commentSessionAvailable,
                  self.amount > 0, !self.isSubmittingTransfer, self.transferPreviewController == nil,
                  let balance = self.walletBalance, self.amount <= balance else { return }
            let data = self.currentPresentationData(for: component)
            let amount = self.amount
            let recipientAddress = self.recipientAddress
            let amountText = formatTonAmountText(amount, dateTimeFormat: data.initial.dateTimeFormat, maxDecimalPositions: 9, formatString: data.initial.strings.Currency_Grams)
            self.finishOpening(animated: true)
            let alert = textAlertController(context: component.context, title: data.initial.strings.Wallet_Send_Title, text: amountText, actions: [
                TextAlertAction(type: .genericAction, title: data.initial.strings.Common_Cancel, action: {}),
                TextAlertAction(type: .defaultAction, title: data.initial.strings.Wallet_Send_Amount(amountText).string, action: { [weak self, weak controller] in
                    guard let self, let controller, self.isVisible, self.commentSessionAvailable, !self.isSubmittingTransfer else { return }
                    self.isSubmittingTransfer = true
                    let transferId = UUID().uuidString
                    let result = VisualGramLocalAppearance.shared.transferLocalGrams(
                        accountId: component.context.account.peerId, toAddress: recipientAddress, amount: amount,
                        comment: self.comment, now: Int32(clamping: Int64(Date().timeIntervalSince1970)), transferId: transferId
                    )
                    if result == .sent {
                        self.closeAfterTransferRegistration(transferId, component: component, controller: controller)
                    } else {
                        self.isSubmittingTransfer = false
                        self.requestUpdate(transition: .immediate)
                        let text = result == .insufficientBalance ? data.initial.strings.Wallet_Send_InsufficientFunds : data.initial.strings.Wallet_Transfer_ErrorText
                        controller.present(textAlertController(context: component.context, title: data.initial.strings.Wallet_Transfer_ErrorTitle, text: text, actions: [
                            TextAlertAction(type: .defaultAction, title: data.initial.strings.Common_OK, action: {})
                        ]), in: .window(.root))
                    }
                })
            ])
            self.transferPreviewController = alert
            controller.present(alert, in: .window(.root))
        }

        /// A send while transfers are faked""")
    replace(source, "                      controller?.peerTransferSubmission != nil else {", "                      (component.visualGram || controller?.peerTransferSubmission != nil) else {")
    replace(source, "                let stillExists = component.walletContext.stateValue.transactions.items.contains(where: {", "                let stillExists = component.visualGram || component.walletContext.stateValue.transactions.items.contains(where: {")
    replace(source, "                let observedWalletContext = component.walletContext\n", """                if component.visualGram {
                    self.walletDisposable.set((VisualGramLocalAppearance.shared.changes |> deliverOnMainQueue).start(next: { [weak self] _ in
                        guard let self else { return }
                        self.walletBalance = VisualGramLocalAppearance.shared.localGramBalance(accountId: component.context.account.peerId)
                        self.walletIsLoading = false
                        if !self.isUpdating { self.requestUpdate(transition: .easeInOut(duration: 0.2)) }
                    }))
                } else {
                let observedWalletContext = component.walletContext
""")
    replace(source, "                }))\n            }\n\n            if self.isVisible {\n                self.resolvePeerAddressIfNeeded()", "                }))\n                }\n            }\n\n            if self.isVisible {\n                self.resolvePeerAddressIfNeeded()")
    replace(source, "                        isLoading: recipientDisplay == .loading,", "                        isLoading: !component.visualGram && recipientDisplay == .loading,")
    replace(source, "                        unavailableText: recipientDisplay == .unavailable", "                        unavailableText: !component.visualGram && recipientDisplay == .unavailable")
    replace(source, "                && self.walletInfo != nil\n", "                && (component.visualGram || self.walletInfo != nil)\n")
    replace(source, "    private var refreshBalanceOnOpen: Bool", "    private var refreshBalanceOnOpen: Bool\n    private let visualGram: Bool")
    replace(source, "        peer: EnginePeer,\n        walletContext: WalletContext,", "        peer: EnginePeer,\n        walletContext: WalletContext,\n        visualGram: Bool = false,")
    replace(source, "        self.refreshBalanceOnOpen = refreshBalanceOnOpen", "        self.refreshBalanceOnOpen = refreshBalanceOnOpen\n        self.visualGram = visualGram", expected=2)
    replace(source, "        address: String,\n        initialAmountNanograms: Int64? = nil,\n        refreshBalanceOnOpen: Bool = true,\n        transferAnimation: WalletSendTransferAnimation? = nil,\n        completed: (() -> Void)? = nil\n    ) {\n        self.walletContext = walletContext\n        self.refreshBalanceOnOpen = refreshBalanceOnOpen\n        self.visualGram = visualGram", "        address: String,\n        initialAmountNanograms: Int64? = nil,\n        refreshBalanceOnOpen: Bool = true,\n        transferAnimation: WalletSendTransferAnimation? = nil,\n        completed: (() -> Void)? = nil\n    ) {\n        self.walletContext = walletContext\n        self.refreshBalanceOnOpen = refreshBalanceOnOpen\n        self.visualGram = false")
    replace(source, "                peer: peer,\n                resolvedAddress:", "                peer: peer,\n                visualGram: visualGram,\n                resolvedAddress:")
    replace(source, "        address: String,\n        initialAmountNanograms: Int64? = nil,", "        address: String,\n        visualGram: Bool = false,\n        initialAmountNanograms: Int64? = nil,")
    replace(source, "        self.visualGram = false\n", "        self.visualGram = visualGram\n")
    replace(source, "                peer: nil,\n                resolvedAddress: nil,", "                peer: nil,\n                visualGram: visualGram,\n                resolvedAddress: nil,")
    replace(source, "                if !component.initialAddress.isEmpty {\n                    self.applyRecipient(component.initialAddress)", """                if component.visualGram {
                    let address = component.peer.map { VisualGramLocalAppearance.visualWalletAddress(peerId: $0.id) }
                        ?? visualGramTransferAddress(component.initialAddress) ?? ""
                    self.updateRecipient(address: address, publicKey: nil)
                } else if !component.initialAddress.isEmpty {
                    self.applyRecipient(component.initialAddress)""")
    replace(source, "            let presentationData = self.currentPresentationData(for: component).initial\n            let title: String", """            let presentationData = self.currentPresentationData(for: component).initial
            if component.visualGram {
                let receive = component.context.sharedContext.makeWalletReceiveScreen(context: component.context, address: self.recipientAddress, isOwnWallet: false)
                if let parent = (controller as? AttachmentContainable)?.parentController() {
                    parent.push(receive)
                } else {
                    controller.push(receive)
                }
                return
            }
            let title: String""")
    replace(source, "        if self.gaslessInfoDisposable == nil {", "        guard !self.visualGram else { return }\n        if self.gaslessInfoDisposable == nil {")


def apply_wallet_dashboard(ui):
    wallet = ui / "Components/Wallet"
    screen = wallet / "WalletScreen/Sources/WalletScreen.swift"
    replace(screen, "    let opensCollectibles: Bool\n", "    let opensCollectibles: Bool\n    let visualGram: Bool\n")
    replace(screen, "        opensCollectibles: Bool\n", "        opensCollectibles: Bool,\n        visualGram: Bool\n")
    replace(screen, "        self.opensCollectibles = opensCollectibles", "        self.opensCollectibles = opensCollectibles\n        self.visualGram = visualGram")
    replace(screen, "            && lhs.opensCollectibles == rhs.opensCollectibles", "            && lhs.opensCollectibles == rhs.opensCollectibles\n            && lhs.visualGram == rhs.visualGram")
    replace(screen, "    private let walletContext: WalletContext\n", "    private let walletContext: WalletContext\n    private let visualGram: Bool\n")
    replace(screen, "        opensCollectibles: Bool = false\n", "        opensCollectibles: Bool = false,\n        visualGram: Bool = false\n")
    replace(screen, "        self.walletContext = walletContext\n        let updatedPresentationData", "        self.walletContext = walletContext\n        self.visualGram = visualGram\n        let updatedPresentationData")
    replace(screen, "                opensCollectibles: opensCollectibles\n", "                opensCollectibles: opensCollectibles,\n                visualGram: visualGram\n")
    replace(screen, "        if self.walletScreenUpdatesDisposable == nil {", "        if !self.visualGram && self.walletScreenUpdatesDisposable == nil {")
    replace(screen, "        componentView.refreshTwoStepAuth()\n        componentView.reloadPreviousWallets()", "        if !self.visualGram {\n            componentView.refreshTwoStepAuth()\n            componentView.reloadPreviousWallets()\n        }")
    replace(screen, "                self.walletStateDisposable = (subscribedContext.state", """                let walletState = component.visualGram ? visualGramWalletState(context: component.context) : subscribedContext.state
                self.walletStateDisposable = (walletState""")
    replace(screen, "                    if previousPhase != walletState.phase || previousWalletAddress != walletState.walletAddress {", "                    if !component.visualGram && (previousPhase != walletState.phase || previousWalletAddress != walletState.walletAddress) {")
    replace(screen, "            if self.twoStepAuthData !== component.context.twoStepAuthData {", "            if !component.visualGram && self.twoStepAuthData !== component.context.twoStepAuthData {")
    replace(screen, "            guard let walletAddress = self.walletAddress else {\n                return\n            }\n            let walletContext = component.walletContext\n            controller.push", """            if component.visualGram {
                controller.push(component.context.sharedContext.makeWalletReceiveScreen(context: component.context, address: VisualGramLocalAppearance.visualWalletAddress(peerId: component.context.account.peerId)))
                return
            }
            guard let walletAddress = self.walletAddress else {
                return
            }
            let walletContext = component.walletContext
            controller.push""")
    replace(screen, "                  self.walletAddress != nil,\n                  !self.isResolvingSigningAccess", "                  (component.visualGram || self.walletAddress != nil),\n                  !self.isResolvingSigningAccess")
    replace(screen, "            guard let walletInfo = self.walletInfo else {\n                self.routeToSend", """            if component.visualGram {
                self.routeToSend(address: address)
                return
            }
            guard let walletInfo = self.walletInfo else {
                self.routeToSend""")
    replace(screen, "                    walletContext: component.walletContext,\n                    transferAnimation:", "                    walletContext: component.walletContext,\n                    visualGram: component.visualGram,\n                    transferAnimation:")
    replace(screen, "                    isEnabled: walletAddress != nil,", "                    isEnabled: component.visualGram || walletAddress != nil,")
    replace(screen, "                    isEnabled: walletAddress != nil &&", "                    isEnabled: (component.visualGram || walletAddress != nil) &&")
    replace(screen, "            let menuItems = component.walletContext.tonConnectState", """            let menuItems: Signal<ContextController.Items, NoError>
            if component.visualGram {
                menuItems = .single(ContextController.Items(content: .list(Array(items.suffix(1)))))
            } else {
            menuItems = component.walletContext.tonConnectState""")
    replace(screen, "            let contextController = makeContextController(\n                presentationData: presentationData,\n                source: .reference(WalletContextReferenceContentSource", "            }\n            let contextController = makeContextController(\n                presentationData: presentationData,\n                source: .reference(WalletContextReferenceContentSource")
    replace(screen, "                walletContext: component.walletContext,\n                transaction: transaction,\n                fromChat: false,", "                walletContext: component.visualGram ? nil : component.walletContext,\n                transaction: transaction,\n                fromChat: false,\n                visualGram: component.visualGram,\n                visualTransactions: component.visualGram ? (self.walletState?.transactions.items.filter(\\.isVisibleInWalletHistory) ?? []) : nil,")
    replace(screen, """            self.giftStickers.update(context: component.context, wallet: component.walletContext,
                state: self.walletState, card: self.card.view as? WalletCardComponent.View, visible: environment.isVisible)""", """            self.giftStickers.update(context: component.context, wallet: component.walletContext,
                state: self.walletState, card: self.card.view as? WalletCardComponent.View, visible: environment.isVisible,
                readOnly: component.visualGram)""")
    picker = wallet / "WalletPeerSelectionScreen/Sources/WalletPeerSelectionScreen.swift"
    replace(picker, "    let mode: WalletPeerSelectionScreenMode\n", "    let mode: WalletPeerSelectionScreenMode\n    let visualGram: Bool\n")
    replace(picker, "        mode: WalletPeerSelectionScreenMode,\n        dismissSourceScreen:", "        mode: WalletPeerSelectionScreenMode,\n        visualGram: Bool,\n        dismissSourceScreen:")
    replace(picker, "        self.mode = mode\n        self.dismissSourceScreen", "        self.mode = mode\n        self.visualGram = visualGram\n        self.dismissSourceScreen")
    replace(picker, "            && lhs.mode == rhs.mode\n", "            && lhs.mode == rhs.mode\n            && lhs.visualGram == rhs.visualGram\n")
    replace(picker, "        mode: WalletPeerSelectionScreenMode = .transfer,\n", "        mode: WalletPeerSelectionScreenMode = .transfer,\n        visualGram: Bool = false,\n")
    replace(picker, "                mode: mode,\n                dismissSourceScreen:", "                mode: mode,\n                visualGram: visualGram,\n                dismissSourceScreen:")
    replace(picker, "            self.isResolvingRecipient = !query.isEmpty", "            self.isResolvingRecipient = !query.isEmpty && self.component?.visualGram != true")
    replace(picker, "            self.resolveDisposable.set((component.walletContext.resolveTransferRecipient(query)", "            guard !component.visualGram else { return }\n            self.resolveDisposable.set((component.walletContext.resolveTransferRecipient(query)")
    replace(picker, "                    walletContext: component.walletContext,\n                    resolvedAddress:", "                    walletContext: component.walletContext,\n                    visualGram: component.visualGram,\n                    resolvedAddress:")


    stickers = wallet / "WalletScreen/Sources/WalletGiftStickerCoordinator.swift"
    replace(stickers, "card: WalletCardComponent.View?, visible: Bool) {", "card: WalletCardComponent.View?, visible: Bool, readOnly: Bool = false) {")
    replace(stickers, "        self.canEdit = isWallet\n", "        self.canEdit = isWallet && !readOnly\n")

    transaction = wallet / "WalletTransactionScreen/Sources/WalletTransactionScreen.swift"
    replace(transaction, "        fromChat: Bool,\n        decryptCommentOnOpen: Bool = false,", "        fromChat: Bool,\n        visualGram: Bool = false,\n        visualTransactions: [WalletContext.Transaction]? = nil,\n        decryptCommentOnOpen: Bool = false,")
    replace(transaction, "        self.checkFirstGramsOnAppear = !decryptCommentOnOpen", "        self.checkFirstGramsOnAppear = !visualGram && !decryptCommentOnOpen")
    replace(transaction, "                walletContext: context.walletContext,\n                fromChat: fromChat,", "                walletContext: visualGram ? nil : context.walletContext,\n                fromChat: fromChat,")
    replace(transaction, "            let showsMore = !self.isPreview || (self.isFinishedPreview && self.transaction != nil)", '            let showsMore = self.transaction?.id.hasPrefix("duckgram:") != true && (!self.isPreview || (self.isFinishedPreview && self.transaction != nil))')

    replace(screen, "                    return WalletContext.isTonConnectUrl(value)", """                    if component.visualGram { return visualGramTransferAddress(value) != nil }
                    return WalletContext.isTonConnectUrl(value)""")
    replace(screen, "                if WalletContext.isTonConnectUrl(value) {", """                if component.visualGram {
                    guard let address = visualGramTransferAddress(value) else { return }
                    Queue.mainQueue().after(0.15) {
                        scanner?.dismiss()
                        self.openSend(address: address)
                    }
                } else if WalletContext.isTonConnectUrl(value) {""")
    replace(screen, "            guard let walletAddress,\n", "            guard self.component?.visualGram != true, let walletAddress,\n")
    replace(screen, "            if let address {\n                self.peerAddressDisposable.set", """            if component.visualGram, let address {
                let screen = WalletSendScreen(context: component.context, walletContext: component.walletContext, address: address, visualGram: true, transferAnimation: { [weak self] id, source in
                    return self?.receiveTransferAnimation(id: id, source: source) ?? false
                }, completed: { [weak self] in
                    self?.revealNewTransfer()
                })
                screen.navigationPresentation = .modal
                controller.push(screen)
            } else if let address {
                self.peerAddressDisposable.set""")

    replace(picker, "            guard !component.visualGram else { return }\n            self.resolveDisposable.set", """            if component.visualGram {
                self.recipient = visualGramTransferAddress(query).map { WalletContext.ResolvedTransferRecipient(address: $0, displayName: nil) }
                self.recipientPeer = nil
                self.searchResultsUpdated()
                return
            }
            self.resolveDisposable.set""")
    replace(picker, "            if let recipient = WalletContext.transferRecipient(from: value) {", """            if self.component?.visualGram == true {
                guard let address = visualGramTransferAddress(value) else {
                    self.presentInvalidPasteToast()
                    return
                }
                query = address
            } else if let recipient = WalletContext.transferRecipient(from: value) {""")
    replace(picker, "                    return WalletContext.transferAddress(from: value) != nil\n", "                    return component.visualGram ? visualGramTransferAddress(value) != nil : WalletContext.transferAddress(from: value) != nil\n")
    replace(picker, "                guard let self,\n                      let value,\n                      let recipient = WalletContext.transferRecipient(from: value) else {", """                guard let self, let value else { return }
                if component.visualGram {
                    guard let address = visualGramTransferAddress(value) else { return }
                    let generation = self.actionGeneration
                    Queue.mainQueue().after(0.15) {
                        guard self.actionGeneration == generation else { return }
                        scanner?.dismiss()
                        self.openSendScreen(address: address)
                    }
                    return
                }
                guard let recipient = WalletContext.transferRecipient(from: value) else {""")
    replace(picker, "            self.hasSpaceForPasteButton = availableSize.width - environment.safeInsets.left - environment.safeInsets.right >= 390.0", "            self.hasSpaceForPasteButton = availableSize.width - environment.safeInsets.left - environment.safeInsets.right >= (component.visualGram ? 320.0 : 390.0)")
    replace(picker, "            self.openRecipient(recipient, peer: self.recipientPeer)\n", """            if self.component?.visualGram == true {
                self.openSendScreen(address: recipient.address)
            } else {
                self.openRecipient(recipient, peer: self.recipientPeer)
            }
""")
    replace(picker, "                    address: address,\n                    refreshBalanceOnOpen: false,", "                    address: address,\n                    visualGram: component.visualGram,\n                    refreshBalanceOnOpen: false,")

    pager_start = "private final class WalletTransactionPagerComponent: Component {"
    source_text = transaction.read_text(encoding="utf-8")
    start = source_text.index(pager_start)
    end = source_text.index("private final class WalletTransactionSheetComponent", start)
    pager = source_text[start:end]
    revised_pager = pager.replace("let walletContext: WalletContext\n", "let walletContext: WalletContext?\n").replace("        walletContext: WalletContext,\n", "        walletContext: WalletContext?,\n")
    replace(transaction, pager, revised_pager)
    replace(transaction, "        var initialTransactions = initialState?.items.filter(\\.isVisibleInWalletHistory) ?? []", "        var initialTransactions = visualTransactions ?? initialState?.items.filter(\\.isVisibleInWalletHistory) ?? []")
    replace(transaction, "        if let walletContext {\n            initialComponent = AnyComponent(WalletTransactionPagerComponent(", "        if walletContext != nil || visualTransactions != nil {\n            initialComponent = AnyComponent(WalletTransactionPagerComponent(")
    replace(transaction, "                if displayedFee > 0 {", '                if displayedFee > 0 || transaction.id.hasPrefix("duckgram:") {')
    replace(transaction, "            if isSelfTransfer || (transaction.direction == .outgoing && !transaction.gasless), let feeComponent {", '            if transaction.id.hasPrefix("duckgram:") || isSelfTransfer || (transaction.direction == .outgoing && !transaction.gasless), let feeComponent {')
    replace(transaction, "                    willDismiss: {\n                        (controller() as? ViewControllerComponentContainer)?.requestLayout(", """                    willDismiss: {
                        guard !context.component.transaction.id.hasPrefix("duckgram:") else { return }
                        (controller() as? ViewControllerComponentContainer)?.requestLayout(""")

    history_item = wallet / "WalletTransactionItemComponent/Sources/WalletTransactionItemComponent.swift"
    replace(history_item, "            if !isServiceTransaction, let peer = transaction.peer.peer {", """            if transaction.id.hasPrefix("duckgram:purchase:") {
                subtitleText = component.strings.Stars_Transaction_GiftPurchase
            } else if transaction.id.hasPrefix("duckgram:sale:") {
                subtitleText = component.strings.Stars_Transaction_GiftSale
            } else if transaction.id.hasPrefix("duckgram:transfer:") {
                subtitleText = displayedDirection == .incoming ? component.strings.Wallet_Transaction_IncomingTransfer : component.strings.Wallet_Transaction_OutgoingTransfer
            }
            if !isServiceTransaction, let peer = transaction.peer.peer {""")
    replace(history_item, "            case .unsupported:\n                peerTitle = walletTransactionCounterparty(nil, strings: component.strings)", """            case .unsupported:
                if transaction.id.hasPrefix("duckgram:topUp:") {
                    peerTitle = component.strings.Wallet_Transaction_Deposit
                } else if transaction.id.hasPrefix("duckgram:purchase:") || transaction.id.hasPrefix("duckgram:sale:") {
                    peerTitle = component.strings.Stars_Transaction_Gift_Title
                } else {
                    peerTitle = walletTransactionCounterparty(nil, strings: component.strings)
                }""")
