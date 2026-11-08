"""DuckGram wallet, activation, collectible links and upgrade fixes."""
from prepare_native import replace


def apply_duckgram(root):
    sub = root / 'submodules'
    ui = sub / 'TelegramUI'
    components = ui / 'Components'
    peer = components / 'PeerInfo/PeerInfoScreen/Sources'
    settings = peer / 'PeerInfoSettingsItems.swift'
    replace(settings, '    if let tonState = data.tonState {\n', '''    let duckGramWallet = VisualGramLocalAppearance.shared.appearance(accountId: context.account.peerId)
    if duckGramWallet.enabled, let grams = duckGramWallet.grams {
        let formatted = formatTonAmountText(grams, dateTimeFormat: presentationData.dateTimeFormat)
        items[.payment]!.append(PeerInfoScreenDisclosureItem(id: 103, label: .text(formatted), text: presentationData.strings.Settings_MyTon, icon: PresentationResourcesSettings.gramEarnings, action: {
            interaction.openSettings(.ton)
        }))
    } else if let tonState = data.tonState {
''')
    actions = peer / 'PeerInfoScreenSettingsActions.swift'
    replace(actions, '''            if let tonContext = self.controller?.tonContext {
                push(self.context.sharedContext.makeStarsTransactionsScreen(context: self.context, starsContext: tonContext))
            }
''', '''            let wallet = VisualGramLocalAppearance.shared.appearance(accountId: self.context.account.peerId)
            if let tonContext = self.controller?.tonContext ?? (wallet.enabled && wallet.grams != nil ? self.context.engine.payments.peerTonContext() : nil) {
                push(self.context.sharedContext.makeStarsTransactionsScreen(context: self.context, starsContext: tonContext))
            }
''')
    stars = components / 'Stars/StarsTransactionsScreen/Sources/StarsTransactionsScreen.swift'
    replace(stars, 'import TelegramPresentationData\n', 'import TelegramPresentationData\nimport PresentationDataUtils\n')
    replace(stars, 'actionAvailable: (!premiumConfiguration.areStarsDisabled && !premiumConfiguration.isPremiumDisabled) && (!component.starsContext.ton || tonWithdrawAvailable),', 'actionAvailable: showLocalGrams || ((!premiumConfiguration.areStarsDisabled && !premiumConfiguration.isPremiumDisabled) && (!component.starsContext.ton || tonWithdrawAvailable)),')
    replace(stars, '                            actionIsEnabled: !showLocalGrams,\n', '                            actionIsEnabled: true,\n')
    replace(stars, '''                                if component.starsContext.ton {
                                    component.withdraw()
''', '''                                if showLocalGrams {
                                    if let controller = environment.controller() {
                                        let alert = textAlertController(context: component.context, title: "Баланс GRAM", text: "Визуальный баланс доступен только в DuckGram.", actions: [TextAlertAction(type: .defaultAction, title: environment.strings.Common_OK, action: {})])
                                        controller.present(alert, in: .window(.root))
                                    }
                                    return
                                }
                                if component.starsContext.ton {
                                    component.withdraw()
''')
    replace(stars, 'presentationData.strings.Stars_Intro_StarsSent(Int32(stars))', 'presentationData.strings.Stars_Intro_StarsSent(Int32(clamping: stars))')
    detail = components / 'Stars/StarsTransactionScreen/Sources/StarsTransactionScreen.swift'
    replace(detail, 'abs(count.amount.value)', 'Int64(clamping: count.amount.value.magnitude)')
    replace(detail, 'abs(count.amount.nanos)', 'Int32(clamping: count.amount.nanos.magnitude)')
    replace(settings, 'abs(starsState.balance.value) > 0', 'starsState.balance.value != 0', expected=2)
    replace(settings, 'abs(tonState.balance.value) > 0', 'tonState.balance.value != 0', expected=2)

    root_controller = ui / 'Sources/TelegramRootController.swift'
    replace(root_controller, 'import TelegramPresentationData\n', 'import TelegramPresentationData\nimport PresentationDataUtils\n')
    replace(root_controller, '    override public func containerLayoutUpdated(', '''    override public func viewDidAppear(_ animated: Bool) {
        super.viewDidAppear(animated)
        VisualGramActivation.shared.start(vendorIdentifier: UIDevice.current.identifierForVendor?.uuidString, isForeground: UIApplication.shared.applicationState != .background, activeNotification: UIApplication.didBecomeActiveNotification, backgroundNotification: UIApplication.didEnterBackgroundNotification)
        Queue.mainQueue().async { [weak self] in
            guard let self, self.viewIfLoaded?.window != nil, self.presentedViewController == nil,
                  UIApplication.shared.applicationState != .background,
                  let window = self.context.sharedContext.mainWindow else { return }
            let defaults = UserDefaults.standard
            let welcomeKey = "DuckGram.didShowWelcome.v1"
            guard !defaults.bool(forKey: welcomeKey) else { return }
            let alert = textAlertController(
                context: self.context,
                title: "Добро пожаловать в DuckGram",
                text: "Трижды нажми на вкладку «Чаты», чтобы открыть меню оформления.",
                actions: [TextAlertAction(type: .defaultAction, title: "Понятно", action: {})]
            )
            // NavigationController.present(_:animated:) traps; use Telegram's window overlay.
            defaults.set(true, forKey: welcomeKey)
            window.present(alert, on: .root)
        }
    }

    override public func containerLayoutUpdated(''')

    account = sub / 'AccountContext/Sources/AccountContext.swift'
    replace(account, '        case gift(StarGift.UniqueGift)\n        case invalidSlug', '        case gift(StarGift.UniqueGift)\n        case duckGramGift(EnginePeer.Id, ProfileGiftsContext.State.StarGift)\n        case invalidSlug')
    urls = sub / 'UrlHandling/Sources/UrlHandling.swift'
    replace(urls, '''        case let .collectible(slug):
            return .single(.progress)''', '''        case let .collectible(slug):
            if slug.hasPrefix("DuckGram_") {
                guard let (owner, gift) = VisualGramLocalAppearance.shared.giftForLocalLink(slug: slug) else {
                    return .single(.result(.collectible(.invalidSlug)))
                }
                return .single(.result(.collectible(.duckGramGift(owner, gift.profileGift(accountId: owner, sender: nil)))))
            }
            return .single(.progress)''')
    opened = ui / 'Sources/OpenResolvedUrl.swift'
    replace(opened, 'import GiftSetupScreen\n', 'import GiftSetupScreen\nimport GiftViewScreen\n')
    replace(opened, '''        case let .collectible(result):
        switch result {
''', '''        case let .collectible(result):
        switch result {
        case let .duckGramGift(owner, gift):
            let controller = GiftViewScreen(context: context, subject: .profileGift(owner, gift))
            navigationController?.pushViewController(controller)
            (contentContext as? StoryProgressPauseContext)?.update(controller)
''')

    core = sub / 'TelegramCore/Sources/TelegramEngine/Payments/StarGifts.swift'
    replace(core, 'public func visualGramGiftCollectionSample(account: Account, giftId: Int64)', 'public func visualGramGiftCollectionSample(account: Account, giftId: Int64, forCrafting: Bool = false)')
    replace(core, 'let catalog = ResaleGiftsContext(account: account, giftId: giftId, forCrafting: false)', 'let catalog = ResaleGiftsContext(account: account, giftId: giftId, forCrafting: forCrafting)')
    replace(core, '''            return _internal_getUniqueStarGift(account: account, slug: candidate.slug)
            |> map { Optional($0) } |> `catch` { _ in .single(nil) }''', '''            if forCrafting, (candidate.craftChancePermille ?? 0) > 0 { return .single(candidate) }
            return _internal_getUniqueStarGift(account: account, slug: candidate.slug)
            |> map { Optional($0) } |> `catch` { _ in .single(nil) }''')
    with core.open('a', encoding='utf-8') as output:
        output.write('''
public func duckGramUpgradeAttributes(account: Account, giftId: Int64) -> Signal<[StarGift.UniqueGift.Attribute]?, NoError> {
    return _internal_getStarGiftUpgradeAttributes(account: account, giftId: giftId)
}

public func duckGramCraftMetadata(account: Account, gift: StarGift.UniqueGift) -> Signal<StarGift.UniqueGift?, NoError> {
    let fallback = visualGramGiftCollectionSample(account: account, giftId: gift.giftId, forCrafting: true)
    if gift.id < 0 && (gift.slug.hasPrefix("DuckGramGift-") || gift.slug.hasPrefix("Gift-")) { return fallback }
    return _internal_getUniqueStarGift(account: account, slug: gift.slug)
    |> map { Optional($0) }
    |> `catch` { _ in .single(nil) }
    |> mapToSignal { exact in
        if let exact, exact.craftChancePermille != nil || exact.flags.contains(.isBurned) { return .single(exact) }
        return fallback
    }
}
''')
    view = components / 'Gifts/GiftViewScreen/Sources/GiftViewScreen.swift'
    replace(view, '        private var visualGramUpgradeTemplate: StarGift.UniqueGift?\n', '        private var visualGramUpgradeTemplate: StarGift.UniqueGift?\n        private var duckGramUpgradeAttributes: [StarGift.UniqueGift.Attribute]?\n')
    text = view.read_text(encoding='utf-8')
    start = text.index('            if case let .profileGift(peerId, localProfile) = subject,')
    end = text.index('            if let arguments = subject.arguments', start)
    text = text[:start] + '''            if let reference = self.visualGramReference,
               case let .message(id) = reference,
               let local = VisualGramLocalAppearance.shared.localGift(accountId: context.account.peerId, reference: reference),
               local.direction == .received, local.isHistoryOnly != true {
                switch local.gift {
                case let .generic(gift) where gift.upgradeStars != nil:
                    self.visualGramMetadata.set((visualGramGiftCollectionSample(account: context.account, giftId: gift.id) |> deliverOnMainQueue).start(next: { [weak self] template in
                        self?.visualGramUpgradeTemplate = template
                    }))
                    self.upgradePreviewDisposable.add((TelegramCore.duckGramUpgradeAttributes(account: context.account, giftId: gift.id) |> deliverOnMainQueue).start(next: { [weak self] attributes in
                        self?.duckGramUpgradeAttributes = attributes
                    }))
                case let .unique(gift) where local.isCrafted != true && local.craftChance == nil && !local.isBurnedCollectible:
                    self.visualGramMetadata.set((duckGramCraftMetadata(account: context.account, gift: gift) |> deliverOnMainQueue).start(next: { [weak self] fresh in
                        guard let self, let fresh else { return }
                        VisualGramLocalAppearance.shared.updateLocalCraftMetadata(accountId: id.peerId, reference: reference, gift: fresh, collectionFallback: fresh.slug != gift.slug)
                        guard let refreshed = VisualGramLocalAppearance.shared.localGift(accountId: context.account.peerId, reference: reference), refreshed.direction == .received, refreshed.isHistoryOnly != true else { return }
                        let sender: EnginePeer?
                        if case let .profileGift(_, profile) = self.subject { sender = profile.fromPeer } else { sender = nil }
                        self.subject = .profileGift(id.peerId, refreshed.profileGift(accountId: id.peerId, sender: sender))
                        self.updated()
                    }))
                default:
                    break
                }
            }
            
''' + text[end:]
    start = text.index('            if self.isVisualGramGift, let arguments = self.subject.arguments, case let .generic(generic) = arguments.gift {', text.index('        func commitUpgrade()'))
    end = text.index('                guard !self.inProgress, self.visualGramCanManage, let reference', start)
    text = text[:start] + '            if self.isVisualGramGift, let arguments = self.subject.arguments, case .generic = arguments.gift {\n' + text[end:]
    text = text.replace('                guard !self.inProgress, self.visualGramCanManage, let reference = self.visualGramReference,', '''                guard !self.inProgress, self.visualGramCanManage else { return }
                let wallet = VisualGramLocalAppearance.shared.appearance(accountId: self.context.account.peerId)
                guard (wallet.stars ?? 0) >= VisualGramLocalAppearance.localGiftUpgradeStars else {
                    let strings = self.context.sharedContext.currentPresentationData.with { $0 }.strings
                    self.getController()?.present(textAlertController(context: self.context, title: nil, text: "Недостаточно звёзд для улучшения", actions: [TextAlertAction(type: .defaultAction, title: strings.Common_OK, action: {})]), in: .window(.root))
                    return
                }
                guard let reference = self.visualGramReference,''', 1)
    text = text.replace('preview: preview, keepOriginalInfo: self.keepOriginalInfo, template: self.visualGramUpgradeTemplate)', 'preview: self.duckGramUpgradeAttributes.map { preview.withAttributes($0) } ?? preview, keepOriginalInfo: self.keepOriginalInfo, template: self.visualGramUpgradeTemplate)', 1)
    text = text.replace('''                if state.isVisualGramGift { upgradeString = strings.Gift_Upgrade_Upgrade }
                let buttonTitle = subject.arguments?.upgradeStars != nil ? strings.Gift_Upgrade_Confirm : upgradeString''', '''                if state.isVisualGramGift {
                    upgradeString = "Улучшить за \\(VisualGramLocalAppearance.localGiftUpgradeStars) звезд"
                }
                let buttonTitle = !state.isVisualGramGift && subject.arguments?.upgradeStars != nil ? strings.Gift_Upgrade_Confirm : upgradeString''', 1)
    start = text.index('        func openMore() {')
    before, menu = text[:start], text[start:]
    menu = menu.replace('            let link = "https://t.me/nft/\\(gift.slug)"', '''            let link: String? = self.isVisualGramGift
                ? VisualGramLocalAppearance.shared.localGiftLink(accountId: context.account.peerId, reference: self.visualGramReference)
                : "https://t.me/nft/\\(gift.slug)"''', 1)
    a = menu.index('                items.append(.action(ContextMenuActionItem(text: presentationData.strings.Gift_View_Context_CopyLink')
    b = menu.index('                items.append(.action(ContextMenuActionItem(text: presentationData.strings.Gift_View_Context_Share', a)
    menu = menu[:a] + '                if let link {\n' + ''.join('    ' + line if line.strip() else line for line in menu[a:b].splitlines(keepends=True)).rstrip() + '\n                }\n\n' + menu[b:]
    text = before + menu
    text = text.replace('if let _ = state.subject.arguments?.canCraftDate {', 'if (!state.isVisualGramGift || state.visualGramCanManage), let _ = state.subject.arguments?.canCraftDate {', 1)
    text = text.replace('if VisualGramLocalAppearance.isLocalReference(self.subject.arguments?.reference), !VisualGramLocalAppearance.shared.canManageLocalGift(accountId: self.context.account.peerId, reference: self.subject.arguments?.reference) { return }', 'if self.isVisualGramGift && !self.visualGramCanManage { return }', 1)
    view.write_text(text, encoding='utf-8', newline='\n')


    setup = components / 'Gifts/GiftSetupScreen/Sources/GiftSetupScreen.swift'
    replace(setup, '            let isSelfGift = component.peerId == component.context.account.peerId\n', '''            let isSelfGift = component.peerId == component.context.account.peerId
            let wallet = VisualGramLocalAppearance.shared.appearance(accountId: component.context.account.peerId)
            let localGiftPayment = wallet.enabled && wallet.stars != nil
''')
    replace(setup, 'environment.strings.Gift_Send_Upgrade("#\\(upgradeStars)")', 'environment.strings.Gift_Send_Upgrade("#\\(localGiftPayment ? VisualGramLocalAppearance.localGiftUpgradeStars : upgradeStars)")')
    replace(setup, '                    finalPrice += upgradePrice\n', '                    finalPrice += localGiftPayment ? VisualGramLocalAppearance.localGiftUpgradeStars : upgradePrice\n')
    replace(setup, '                let amountString = presentationStringsFormattedNumber(Int32(finalPrice),', '                let amountString = presentationStringsFormattedNumber(Int32(clamping: finalPrice),')
    apply_premium_stars(setup, components / 'Gifts/GiftOptionsScreen/Sources/GiftOptionsScreen.swift')


def apply_premium_stars(setup, options):
    replace(setup, 'if self.payWithStars, let starsPrice = product.starsPrice', 'if self.payWithStars || product.giftOption.currency == "XTR", let starsPrice = product.starsPrice', expected=3)
    replace(setup, '                    if let balance = component.context.starsContext?.currentState?.balance, balance.value < starsPrice {', '''                    let wallet = VisualGramLocalAppearance.shared.appearance(accountId: component.context.account.peerId)
                    let localPayment = wallet.enabled && wallet.stars != nil
                    if !localPayment, let balance = component.context.starsContext?.currentState?.balance, balance.value < starsPrice {''')
    replace(setup, '''                                    if let self {
                                        self.proceedWithStarGift()
                                    }
''', '''                                    if let self {
                                        if localPayment {
                                            self.proceedWithLocalPremiumGift(months: product.months, price: starsPrice)
                                        } else {
                                            self.proceedWithStarGift()
                                        }
                                    }
''')
    replace(setup, '        private func proceedWithPremiumGift() {\n', '''        private func proceedWithLocalPremiumGift(months: Int32, price: Int64) {
            guard !self.inProgress, let component = self.component, let environment = self.environment,
                  let controller = environment.controller() else { return }
            let context = component.context
            var caption = NSAttributedString()
            if let input = self.inputPanel.view as? MessageInputPanelComponent.View, case let .text(text) = input.getSendMessageInput() {
                caption = text
            }
            let result = VisualGramLocalAppearance.shared.buyLocalPremiumGift(
                accountId: context.account.peerId, recipientPeerId: component.peerId,
                months: months, price: price, text: caption.string, entities: generateChatInputTextEntities(caption),
                now: Int32(clamping: Int64(Date().timeIntervalSince1970))
            )
            if result == .success {
                self.inProgress = true
                visualGramFinishGift(context: context, peerId: component.peerId, controller: controller, completion: component.completion)
            } else {
                let error = result == .insufficientBalance ? "Недостаточно звёзд" : environment.strings.Gift_Send_ErrorUnknown
                controller.present(textAlertController(context: context, title: nil, text: error, actions: [TextAlertAction(type: .defaultAction, title: environment.strings.Common_OK, action: {})]), in: .window(.root))
            }
        }

        private func proceedWithPremiumGift() {
''')
    replace(setup, '                let balance = component.context.starsContext?.currentState?.balance.value ?? 0\n', '                let balance = (localGiftPayment ? wallet.stars : nil) ?? component.context.starsContext?.currentState?.balance.value ?? 0\n')
    replace(setup, 'presentationStringsFormattedNumber(Int32(balance), environment.dateTimeFormat.groupingSeparator)', 'formatStarsAmountText(StarsAmount(value: balance, nanos: 0), dateTimeFormat: environment.dateTimeFormat)')
    replace(setup, '                    let starsFooterRawString = environment.strings.Gift_Send_PayWithStars_Info("# \\(balanceString)").string', '                    let starsFooterRawString = localGiftPayment ? "# \\(balanceString)" : environment.strings.Gift_Send_PayWithStars_Info("# \\(balanceString)").string')
    replace(setup, 'isOn: self.payWithStars, action:', 'isOn: self.payWithStars || product.giftOption.currency == "XTR", action:')
    replace(setup, '                                        self.payWithStars = !self.payWithStars', '                                        guard product.giftOption.currency != "XTR" else { return }\n                                        self.payWithStars = !self.payWithStars')
    replace(setup, '        return self.storeProduct?.id ?? (self.giftOption.storeProductId ?? "")', '''        if self.giftOption.currency == "XTR" { return "stars-\\(self.months)" }
        return self.storeProduct?.id ?? (self.giftOption.storeProductId ?? "")''')
    # Preserve server Stars-only offers even when the App Store catalog is missing a tier.
    replace(options, '                        self.premiumProducts = premiumProducts.sorted(by: { $0.months < $1.months })', '''                        for option in premiumOptions where option.currency == "XTR" && option.amount > 0 {
                            if !premiumProducts.contains(where: { $0.months == option.months && $0.starsPrice != nil }) {
                                premiumProducts.append(PremiumGiftProduct(giftOption: option, starsGiftOption: option, storeProduct: nil, discount: nil))
                            }
                        }
                        self.premiumProducts = premiumProducts.sorted(by: { $0.months < $1.months })''', expected=2)
