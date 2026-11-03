"""Prevent expired visual purchases from falling through to real Telegram payments."""
from prepare_native import replace

def apply_activation(root):
    buy = root / 'submodules/TelegramUI/Components/Gifts/GiftViewScreen/Sources/GiftViewBuyGift.swift'
    signature = 'func visualGramBuyLocalGift(context: AccountContext, recipientPeerId: EnginePeer.Id, gift: StarGift.UniqueGift, getController: @escaping () -> ViewController?, completion: @escaping () -> Void) -> Bool {\n'
    replace(buy, signature, signature + '''    if VisualGramLocalAppearance.shared.blocksExpiredPurchase(accountId: context.account.peerId, slug: gift.slug) {
        let strings = context.sharedContext.currentPresentationData.with { $0 }.strings
        getController()?.present(textAlertController(context: context, title: "VisualGram", text: "Для локальных покупок активируйте доступ: три нажатия на вкладку «Чаты».", actions: [TextAlertAction(type: .defaultAction, title: strings.Common_OK, action: {})]), in: .window(.root))
        return true
    }
''')
    setup = root / 'submodules/TelegramUI/Components/Gifts/GiftSetupScreen/Sources/GiftSetupScreen.swift'
    needle = '''        private func proceedWithStarGift() {
            guard !self.inProgress, let component = self.component, let environment = self.environment else { return }
'''
    replace(setup, needle, needle + '''            if VisualGramLocalAppearance.shared.blocksExpiredPurchase(accountId: component.context.account.peerId) {
                let strings = component.context.sharedContext.currentPresentationData.with { $0 }.strings
                environment.controller()?.present(textAlertController(context: component.context, title: "VisualGram", text: "Для локальных покупок активируйте доступ: три нажатия на вкладку «Чаты».", actions: [TextAlertAction(type: .defaultAction, title: strings.Common_OK, action: {})]), in: .window(.root))
                return
            }
''')
