from prepare_native import replace


def apply_wallet_send(wallet_send):
    source = wallet_send / "Sources/WalletSendScreen.swift"
    replace(source, "    let peer: EnginePeer?\n    let resolvedAddress:", "    let peer: EnginePeer?\n    let visualGram: Bool\n    let resolvedAddress:")
    replace(source, "        peer: EnginePeer?,\n        resolvedAddress:", "        peer: EnginePeer?,\n        visualGram: Bool = false,\n        resolvedAddress:")
    replace(source, "        self.peer = peer\n        self.resolvedAddress", "        self.peer = peer\n        self.visualGram = visualGram\n        self.resolvedAddress")
    replace(source, "        if lhs.peer != rhs.peer {", "        if lhs.peer != rhs.peer || lhs.visualGram != rhs.visualGram {")
    replace(source, "        private func resolvePeerAddressIfNeeded() {\n", "        private func resolvePeerAddressIfNeeded() {\n            guard self.component?.visualGram != true else { return }\n")
    replace(source, "            guard let walletAddress = self.walletAddress else {\n                return\n            }\n            let receiveController", """            if component.visualGram {
                presentGramTopUp(on: controller, context: component.context, data: self.currentPresentationData(for: component).initial)
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
                  let peer = component.peer, self.isVisible, self.commentSessionAvailable,
                  self.amount > 0, !self.isSubmittingTransfer, self.transferPreviewController == nil,
                  let balance = self.walletBalance, self.amount <= balance else { return }
            let data = self.currentPresentationData(for: component)
            let amount = self.amount
            let amountText = formatTonAmountText(amount, dateTimeFormat: data.initial.dateTimeFormat, maxDecimalPositions: 9, formatString: data.initial.strings.Currency_Grams)
            self.finishOpening(animated: true)
            let alert = textAlertController(context: component.context, title: data.initial.strings.Wallet_Send_Title, text: amountText, actions: [
                TextAlertAction(type: .genericAction, title: data.initial.strings.Common_Cancel, action: {}),
                TextAlertAction(type: .defaultAction, title: data.initial.strings.Wallet_Send_Amount(amountText).string, action: { [weak self, weak controller] in
                    guard let self, let controller, self.isVisible, self.commentSessionAvailable, !self.isSubmittingTransfer else { return }
                    self.isSubmittingTransfer = true
                    let transferId = UUID().uuidString
                    let result = VisualGramLocalAppearance.shared.transferLocalGrams(
                        accountId: component.context.account.peerId, to: peer.id, amount: amount,
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
    replace(source, "            let hasRecipient = !self.recipientAddress.isEmpty", "            let hasRecipient = component.visualGram ? component.peer != nil : !self.recipientAddress.isEmpty")
    replace(source, "                && self.walletInfo != nil\n", "                && (component.visualGram || self.walletInfo != nil)\n")
    replace(source, "    private var refreshBalanceOnOpen: Bool", "    private var refreshBalanceOnOpen: Bool\n    private let visualGram: Bool")
    replace(source, "        peer: EnginePeer,\n        walletContext: WalletContext,", "        peer: EnginePeer,\n        walletContext: WalletContext,\n        visualGram: Bool = false,")
    replace(source, "        self.refreshBalanceOnOpen = refreshBalanceOnOpen", "        self.refreshBalanceOnOpen = refreshBalanceOnOpen\n        self.visualGram = visualGram", expected=2)
    replace(source, "        address: String,\n        initialAmountNanograms: Int64? = nil,\n        refreshBalanceOnOpen: Bool = true,\n        transferAnimation: WalletSendTransferAnimation? = nil,\n        completed: (() -> Void)? = nil\n    ) {\n        self.walletContext = walletContext\n        self.refreshBalanceOnOpen = refreshBalanceOnOpen\n        self.visualGram = visualGram", "        address: String,\n        initialAmountNanograms: Int64? = nil,\n        refreshBalanceOnOpen: Bool = true,\n        transferAnimation: WalletSendTransferAnimation? = nil,\n        completed: (() -> Void)? = nil\n    ) {\n        self.walletContext = walletContext\n        self.refreshBalanceOnOpen = refreshBalanceOnOpen\n        self.visualGram = false")
    replace(source, "                peer: peer,\n                resolvedAddress:", "                peer: peer,\n                visualGram: visualGram,\n                resolvedAddress:")
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
    replace(screen, "            return self.walletState?.walletAddress", "            return self.component?.visualGram == true ? nil : self.walletState?.walletAddress")
    replace(screen, "                self.walletStateDisposable = (subscribedContext.state", """                let walletState = component.visualGram ? visualGramWalletState(context: component.context) : subscribedContext.state
                self.walletStateDisposable = (walletState""")
    replace(screen, "                    if previousPhase != walletState.phase || previousWalletAddress != walletState.walletAddress {", "                    if !component.visualGram && (previousPhase != walletState.phase || previousWalletAddress != walletState.walletAddress) {")
    replace(screen, "            if self.twoStepAuthData !== component.context.twoStepAuthData {", "            if !component.visualGram && self.twoStepAuthData !== component.context.twoStepAuthData {")
    replace(screen, "            guard let walletAddress = self.walletAddress else {\n                return\n            }\n            let walletContext = component.walletContext\n            controller.push", """            if component.visualGram {
                presentGramTopUp(on: controller, context: component.context, data: self.currentPresentationData(for: component).initial)
                return
            }
            guard let walletAddress = self.walletAddress else {
                return
            }
            let walletContext = component.walletContext
            controller.push""")
    replace(screen, "                  self.walletAddress != nil,\n                  !self.isResolvingSigningAccess", "                  (component.visualGram || self.walletAddress != nil),\n                  !self.isResolvingSigningAccess")
    replace(screen, "            guard let walletInfo = self.walletInfo else {\n                self.routeToSend", """            if component.visualGram {
                self.routeToSend(address: nil)
                return
            }
            guard let walletInfo = self.walletInfo else {
                self.routeToSend""")
    replace(screen, "                    walletContext: component.walletContext,\n                    transferAnimation:", "                    walletContext: component.walletContext,\n                    visualGram: component.visualGram,\n                    transferAnimation:")
    replace(screen, "                    isEnabled: walletAddress != nil,", "                    isEnabled: component.visualGram || walletAddress != nil,")
    replace(screen, "                    isEnabled: walletAddress != nil &&", "                    isEnabled: (component.visualGram || walletAddress != nil) &&")
    replace(screen, "                ),\n                NavigationBarComponent.Button(\n                    id: \"scanQr\",", "                )\n            ] + (component.visualGram ? [] : [\n                NavigationBarComponent.Button(\n                    id: \"scanQr\",")
    replace(screen, "                    accessibilityLabel: environment.strings.Contacts_ScanQrCode\n                )\n            ]", "                    accessibilityLabel: environment.strings.Contacts_ScanQrCode\n                )\n            ])")
    replace(screen, "            let menuItems = component.walletContext.tonConnectState", """            let menuItems: Signal<ContextController.Items, NoError>
            if component.visualGram {
                menuItems = .single(ContextController.Items(content: .list(Array(items.suffix(1)))))
            } else {
            menuItems = component.walletContext.tonConnectState""")
    replace(screen, "            let contextController = makeContextController(\n                presentationData: presentationData,\n                source: .reference(WalletContextReferenceContentSource", "            }\n            let contextController = makeContextController(\n                presentationData: presentationData,\n                source: .reference(WalletContextReferenceContentSource")
    replace(screen, "                walletContext: component.walletContext,\n                transaction: transaction,\n                fromChat: false,", "                walletContext: component.visualGram ? nil : component.walletContext,\n                transaction: transaction,\n                fromChat: false,\n                visualGram: component.visualGram,")
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
    replace(picker, "            alphaTransition.setAlpha(view: self.scanQrButton, alpha: alpha)\n", "            alphaTransition.setAlpha(view: self.scanQrButton, alpha: self.component?.visualGram == true ? 0.0 : alpha)\n")
    replace(picker, "            self.scanQrButton.isUserInteractionEnabled = buttonsAreInteractive", "            self.scanQrButton.isUserInteractionEnabled = buttonsAreInteractive && self.component?.visualGram != true")
    replace(picker, "            self.hasSpaceForPasteButton = availableSize", "            self.hasSpaceForPasteButton = !component.visualGram && availableSize")

    replace(screen, "                    qrAccessibilityLabel: environment.strings.Wallet_Receive_ShowQR", "                    qrAccessibilityLabel: environment.strings.Wallet_Receive_ShowQR,\n                    showsQr: !component.visualGram")
    card = wallet / "WalletCardComponent/Sources/WalletCardComponent.swift"
    replace(card, "    public let qrAccessibilityLabel: String?\n", "    public let qrAccessibilityLabel: String?\n    public let showsQr: Bool\n")
    replace(card, "        qrAccessibilityLabel: String? = nil\n", "        qrAccessibilityLabel: String? = nil,\n        showsQr: Bool = true\n")
    replace(card, "        self.qrAccessibilityLabel = qrAccessibilityLabel\n", "        self.qrAccessibilityLabel = qrAccessibilityLabel\n        self.showsQr = showsQr\n")
    replace(card, "        if lhs.qrAccessibilityLabel != rhs.qrAccessibilityLabel {", "        if lhs.qrAccessibilityLabel != rhs.qrAccessibilityLabel || lhs.showsQr != rhs.showsQr {")
    replace(card, "            let balanceRightEdge = qrFrame.minX - 10.0 * scale", "            let balanceRightEdge = component.showsQr ? qrFrame.minX - 10.0 * scale : width - 32.0 * scale")
    replace(card, "            if let qrView = self.qrButton.view {\n                if qrView.superview !== self.foregroundView {", "            if let qrView = self.qrButton.view {\n                qrView.isHidden = !component.showsQr\n                if qrView.superview !== self.foregroundView {")
    replace(card, "            self.qrAlpha = detailsAlpha\n", "            self.qrAlpha = self.component?.showsQr == false ? 0.0 : detailsAlpha\n")

    stickers = wallet / "WalletScreen/Sources/WalletGiftStickerCoordinator.swift"
    replace(stickers, "card: WalletCardComponent.View?, visible: Bool) {", "card: WalletCardComponent.View?, visible: Bool, readOnly: Bool = false) {")
    replace(stickers, "        self.canEdit = isWallet\n", "        self.canEdit = isWallet && !readOnly\n")

    transaction = wallet / "WalletTransactionScreen/Sources/WalletTransactionScreen.swift"
    replace(transaction, "        fromChat: Bool,\n        decryptCommentOnOpen: Bool = false,", "        fromChat: Bool,\n        visualGram: Bool = false,\n        decryptCommentOnOpen: Bool = false,")
    replace(transaction, "        self.checkFirstGramsOnAppear = !decryptCommentOnOpen", "        self.checkFirstGramsOnAppear = !visualGram && !decryptCommentOnOpen")
    replace(transaction, "                walletContext: context.walletContext,\n                fromChat: fromChat,", "                walletContext: visualGram ? nil : context.walletContext,\n                fromChat: fromChat,")
    replace(transaction, "            let showsMore = !self.isPreview || (self.isFinishedPreview && self.transaction != nil)", '            let showsMore = self.transaction?.id.hasPrefix("duckgram:") != true && (!self.isPreview || (self.isFinishedPreview && self.transaction != nil))')

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
