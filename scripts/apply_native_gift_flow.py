"""Unify local gift completion, ordinary purchases, native wording and balance UI."""
import shutil
from prepare_native import replace


def apply_gift_flow(root, project):
    protocol = root / 'submodules/AccountContext/Sources/Premium.swift'
    with protocol.open('a', encoding='utf-8') as handle:
        handle.write('\npublic protocol VisualGramGiftFlowController: AnyObject {\n    var visualGramGiftCompletion: (() -> Void)? { get set }\n}\n')
    gift_path = 'submodules/TelegramUI/Components/Gifts/'
    shutil.copyfile(project / 'native/VisualGramGiftFlow.swift', root / gift_path / 'GiftViewScreen/Sources/VisualGramGiftFlow.swift')
    shutil.copyfile(project / 'native/VisualGramGiftPurchaseAttribute.swift', root / 'submodules/TelegramCore/Sources/VisualGramGiftPurchaseAttribute.swift')
    service = root / 'submodules/TelegramStringFormatting/Sources/ServiceMessageStrings.swift'
    replace(service, '                    if isAuctionAcquired {\n', '''                    if message.id.namespace == Int32.max - 42, let purchase = message._asMessage().attributes.compactMap({ $0 as? VisualGramGiftPurchaseAttribute }).first {
                        let starsString = strings.Notification_StarsGift_Bought_Stars(Int32(clamping: purchase.stars))
                        if message.author?.id == accountPeerId || !message._asMessage().flags.contains(.Incoming) {
                            if message.id.peerId == accountPeerId {
                                attributedString = addAttributesToStringWithRanges(strings.Notification_StarsGift_BoughtForYouself(starsString)._tuple, body: bodyAttributes, argumentAttributes: [0: boldAttributes])
                            } else {
                                attributedString = addAttributesToStringWithRanges(strings.Notification_StarsGift_BoughtYou(strings.Notification_Gift, starsString)._tuple, body: bodyAttributes, argumentAttributes: [0: boldAttributes, 1: boldAttributes])
                            }
                        } else {
                            var attributes = peerMentionsAttributes(primaryTextColor: primaryTextColor, peerIds: peerIds)
                            attributes[1] = boldAttributes
                            attributes[2] = boldAttributes
                            attributedString = addAttributesToStringWithRanges(strings.Notification_StarsGift_Bought(authorName, strings.Notification_Gift, starsString)._tuple, body: bodyAttributes, argumentAttributes: attributes)
                        }
                    } else if isAuctionAcquired {
''')
    # Preserve the attachment owner's dismissal callback when navigating into the market.
    options = root / gift_path / 'GiftOptionsScreen/Sources/GiftOptionsScreen.swift'
    replace(options, 'open class GiftOptionsScreen: ViewControllerComponentContainer, GiftOptionsScreenProtocol {', 'open class GiftOptionsScreen: ViewControllerComponentContainer, GiftOptionsScreenProtocol, VisualGramGiftFlowController {\n    public var visualGramGiftCompletion: (() -> Void)?\n')
    replace(options, '        super.init(context: context, component: GiftOptionsScreenComponent(', '        self.visualGramGiftCompletion = completion\n        super.init(context: context, component: GiftOptionsScreenComponent(')
    # The synchronous local transaction must finish AFTER callbacks are installed.
    replace(options, '                    let proceed: (Bool) -> Void = { waitForTopUp in\n', '''                    if VisualGramLocalAppearance.isLocalReference(reference) {
                        guard let mainController else { return }
                        guard VisualGramLocalAppearance.shared.transferLocalGift(accountId: context.account.peerId, reference: reference, recipientPeerId: peer.id, now: Int32(clamping: Int64(Date().timeIntervalSince1970))) else {
                            dismissAlertImpl?()
                            mainController.present(textAlertController(context: context, title: nil, text: presentationData.strings.Gift_Send_ErrorUnknown, actions: [TextAlertAction(type: .defaultAction, title: presentationData.strings.Common_OK, action: {})]), in: .window(.root))
                            return
                        }
                        dismissAlertImpl?()
                        visualGramFinishGift(context: context, peerId: peer.id, controller: mainController, completion: component.completion)
                        return
                    }
                    let proceed: (Bool) -> Void = { waitForTopUp in
''')
    # All pushes from this screen pass its completion along to a market controller.
    text = options.read_text(encoding='utf-8')
    needle = 'mainController.push(component.context.sharedContext.makeGiftStoreController(context: component.context, peerId: component.peerId, gift: gift))'
    replacement = '''let market = component.context.sharedContext.makeGiftStoreController(context: component.context, peerId: component.peerId, gift: gift)
                        (market as? VisualGramGiftFlowController)?.visualGramGiftCompletion = component.completion
                        mainController.push(market)'''
    if needle not in text:
        raise ValueError('Gift market push changed')
    text = text.replace(needle, replacement)
    text = text.replace('                                mainController.push(storeController)\n', '                                (storeController as? VisualGramGiftFlowController)?.visualGramGiftCompletion = component.completion\n                                mainController.push(storeController)\n')
    # A configured Premium badge also allows locally purchasing Premium-only gifts.
    text = text.replace('!component.context.isPremium && !((gift.availability?.resale ?? 0) > 0)', '!component.context.isPremium && !(VisualGramLocalAppearance.shared.appearance(accountId: component.context.account.peerId).enabled && VisualGramLocalAppearance.shared.appearance(accountId: component.context.account.peerId).premium) && !((gift.availability?.resale ?? 0) > 0)')
    options.write_text(text, encoding='utf-8')

    market = root / gift_path / 'GiftStoreScreen/Sources/GiftStoreScreen.swift'
    replace(market, 'public class GiftStoreScreen: ViewControllerComponentContainer {', 'public class GiftStoreScreen: ViewControllerComponentContainer, VisualGramGiftFlowController {\n    public var visualGramGiftCompletion: (() -> Void)?\n')
    replace(market, '                                                mainController.push(giftController)\n', '                                                giftController.visualGramGiftCompletion = (controller as? VisualGramGiftFlowController)?.visualGramGiftCompletion\n                                                mainController.push(giftController)\n')

    screen = root / gift_path / 'GiftViewScreen/Sources/GiftViewScreen.swift'
    text = screen.read_text(encoding='utf-8')
    # The picker already navigates on success; dismissing its parent caused the second transition.
    text = text.replace('completion: { [weak self, weak controller] peerIds in\n                        guard let self, let recipient = peerIds.first else { return .complete() }', 'completion: { [weak self] peerIds in\n                        guard let self, let recipient = peerIds.first else { return .fail(.generic) }')
    text = text.replace('                            return .complete()\n                        }\n                        self.updated(transition: .immediate)\n                        controller?.dismissAnimated()\n', '                            return .fail(.generic)\n                        }\n                        self.updated(transition: .immediate)\n')
    start = text.index('            if case let .unique(gift) = self.subject.arguments?.gift, visualGramBuyLocalGift(')
    end = text.index('            guard !self.isVisualGramGift else { return }', start)
    text = text[:start] + '''            if case let .unique(gift) = self.subject.arguments?.gift, visualGramBuyLocalGift(context: self.context, recipientPeerId: self.recipientPeerId ?? self.context.account.peerId, gift: gift, getController: self.getController, completion: {}) { return }
''' + text[end:]
    # Class declaration has upstream protocols; append ours without replacing them.
    declaration = next(line for line in text.splitlines() if line.startswith('public class GiftViewScreen:'))
    text = text.replace(declaration, declaration[:-1].rstrip() + ', VisualGramGiftFlowController {\n    public var visualGramGiftCompletion: (() -> Void)?\n    public var visualGramPreview = false')
    text = text.replace('controller.customAction?.title.hasSuffix("локально") == true', 'controller.visualGramPreview')
    screen.write_text(text, encoding='utf-8')

    purchase_alert = root / gift_path / 'GiftViewScreen/Sources/GiftPurchaseAlertController.swift'
    replace(purchase_alert, '    dismissed: @escaping () -> Void\n', '    dismissed: @escaping () -> Void,\n    starsOnly: Bool = false\n')
    replace(purchase_alert, 'if gift.resellForTonOnly {', 'if gift.resellForTonOnly && !starsOnly {', expected=2)
    replace(purchase_alert, '        } else {\n            content.append(AnyComponentWithIdentity(\n                id: "currency",', '        } else if !starsOnly {\n            content.append(AnyComponentWithIdentity(\n                id: "currency",')

    shared = root / 'submodules/TelegramUI/Sources/SharedAccountContext.swift'
    # Only local transfers use this early completion. The real transfer code stays intact.
    text = shared.read_text(encoding='utf-8')
    start = text.index('        presentTransferAlertImpl = { [weak controller] peer in')
    transfer = text[start:]
    old = '                                var controllers = navigationController.viewControllers\n                                controllers = controllers.filter { !($0 is ContactSelectionController) }\n'
    if transfer.count(old) != 1:
        raise ValueError('Gift picker completion changed')
    transfer = transfer.replace(old, '''                                if case let .starGiftTransfer(_, reference, _, _, _, _) = source, VisualGramLocalAppearance.isLocalReference(reference) {
                                    visualGramFinishGift(context: context, peerId: peer.id, controller: controller)
                                    return
                                }
                                var controllers = navigationController.viewControllers
                                controllers = controllers.filter { !($0 is ContactSelectionController) }
''', 1)
    shared.write_text(text[:start] + transfer, encoding='utf-8')
    # Local cards receive one explicit confetti effect from the completion helper.
    bubble = root / 'submodules/TelegramUI/Components/Chat/ChatMessageGiftBubbleContentNode/Sources/ChatMessageGiftBubbleContentNode.swift'
    replace(bubble, '            if !alreadySeen && self.animationNode.isPlaying {\n', '            if !alreadySeen && self.animationNode.isPlaying && item.message.id.namespace != Int32.max - 42 {\n')

    setup = root / gift_path / 'GiftSetupScreen/Sources/GiftSetupScreen.swift'
    replace(setup, 'import Foundation\n', 'import Foundation\nimport GiftViewScreen\n')
    build = root / gift_path / 'GiftSetupScreen/BUILD'
    replace(build, '    deps = [\n', '    deps = [\n        "//submodules/TelegramUI/Components/Gifts/GiftViewScreen",\n')
    replace(setup, '            guard let component = self.component, let environment = self.environment, let starsContext = component.context.starsContext, let starsState = starsContext.currentState else {\n', '''            guard let component = self.component, let environment = self.environment else { return }
            if case let .starGift(gift, _) = component.subject {
                let appearance = VisualGramLocalAppearance.shared.appearance(accountId: component.context.account.peerId)
                if appearance.enabled, appearance.stars != nil {
                    self.proceedWithVisualGramGift(gift)
                    return
                }
            }
            guard let starsContext = component.context.starsContext, let starsState = starsContext.currentState else {
''')
    replace(setup, '        private func proceedWithStarGift() {\n', ORDINARY_BUY + '\n        private func proceedWithStarGift() {\n')
    replace(setup, '                                        controller.push(storeController)\n', '                                        (storeController as? VisualGramGiftFlowController)?.visualGramGiftCompletion = component.completion\n                                        controller.push(storeController)\n')


ORDINARY_BUY = r'''
        private func proceedWithVisualGramGift(_ gift: StarGift.Gift) {
            guard !self.inProgress, let component = self.component, let environment = self.environment, let controller = environment.controller() else { return }
            let context = component.context
            let text: String
            if let input = self.inputPanel.view as? MessageInputPanelComponent.View, case let .text(value) = input.getSendMessageInput() { text = value.string } else { text = "" }
            let upgrade = self.includeUpgrade
            self.inProgress = true
            self.state?.updated()
            let commit: (StarGiftUpgradePreview?) -> Void = { [weak self, weak controller] preview in
                guard let self, let controller else { return }
                let result = VisualGramLocalAppearance.shared.buyLocalOrdinaryGift(accountId: context.account.peerId, recipientPeerId: component.peerId, gift: gift, text: text, includeUpgrade: upgrade, preview: preview, hasPremium: context.isPremium, now: Int32(clamping: Int64(Date().timeIntervalSince1970)))
                self.inProgress = false
                self.state?.updated()
                if result == .success {
                    visualGramFinishGift(context: context, peerId: component.peerId, controller: controller, completion: component.completion)
                } else {
                    let strings = context.sharedContext.currentPresentationData.with { $0 }.strings
                    let error = result == .unavailable ? strings.Gift_Send_ErrorOutOfStock : (result == .insufficientBalance ? "Недостаточно звёзд" : strings.Gift_Send_ErrorUnknown)
                    controller.present(textAlertController(context: context, title: nil, text: error, actions: [TextAlertAction(type: .defaultAction, title: strings.Common_OK, action: {})]), in: .window(.root))
                }
            }
            if upgrade {
                let _ = (context.engine.payments.starGiftUpgradePreview(giftId: gift.id) |> take(1) |> deliverOnMainQueue).start(next: commit)
            } else { commit(nil) }
        }
'''
