"""Hidden menu gesture and local Stars history without altering real payment state."""
import shutil
from prepare_native import replace


def apply_stars_history(root, project):
    core = root / 'submodules/TelegramCore/Sources'
    for name in ['VisualGramStarsHistory.swift', 'VisualGramTabTapCounter.swift']:
        shutil.copyfile(project / 'native' / name, core / name)
    view = root / 'submodules/Display/Source/ViewController.swift'
    replace(view, '    public var tabBarItemDebugTapAction: (() -> Void)?\n', '    public var tabBarItemDebugTapAction: (() -> Void)?\n    public var tabBarItemTapAction: (() -> Bool)?\n')
    tabs = root / 'submodules/TabBarUI/Sources/TabBarController.swift'
    replace(tabs, '                let timestamp = CACurrentMediaTime()\n', '                if !longTap, strongSelf.controllers[index].tabBarItemTapAction?() == true { return }\n                let timestamp = CACurrentMediaTime()\n')
    root_controller = root / 'submodules/TelegramUI/Sources/TelegramRootController.swift'
    replace(root_controller, '    private let context: AccountContext\n', '    private let context: AccountContext\n    private var visualGramChatsTaps = VisualGramTabTapCounter()\n')
    replace(root_controller, '        accountSettingsController.parentController = self\n        controllers.append(accountSettingsController)\n', '''        accountSettingsController.parentController = self
        controllers.append(accountSettingsController)
        for controller in controllers {
            controller.tabBarItemTapAction = { [weak self] in
                self?.visualGramChatsTaps.reset()
                return false
            }
        }
        chatListController.tabBarItemTapAction = { [weak self] in
            guard let self else { return false }
            guard self.visualGramChatsTaps.tap(now: ProcessInfo.processInfo.systemUptime) else { return false }
            self.pushViewController(visualGramAppearanceController(context: self.context))
            return true
        }
''')
    appearance = root / 'submodules/TelegramUI/Components/PeerInfo/PeerInfoScreen/Sources/VisualGramAppearanceController.swift'
    replace(appearance, 'func visualGramAppearanceController(context: AccountContext) -> ViewController {', 'public func visualGramAppearanceController(context: AccountContext) -> ViewController {')

    stars = core / 'TelegramEngine/Payments/Stars.swift'
    text = stars.read_text(encoding='utf-8')
    start = text.index('public final class StarsTransactionsContext {')
    end = text.index('private final class StarsSubscriptionsContextImpl', start)
    part = text[start:end]
    part = part.replace('    fileprivate let impl: QueueLocalObject<StarsTransactionsContextImpl>\n', '    fileprivate let impl: QueueLocalObject<StarsTransactionsContextImpl>\n    private let visualGramAccount: Account\n    private let visualGramMode: Mode\n', 1)
    part = part.replace('    public var state: Signal<StarsTransactionsContext.State, NoError> {\n        return Signal { subscriber in', '''    public var state: Signal<StarsTransactionsContext.State, NoError> {
        return combineLatest(self.visualGramServerState, VisualGramLocalAppearance.shared.changes)
        |> mapToSignal { state, _ -> Signal<StarsTransactionsContext.State, NoError> in
            let account = self.visualGramAccount
            let appearance = VisualGramLocalAppearance.shared.appearance(accountId: account.peerId)
            guard !self.ton, self.peerId == account.peerId, appearance.enabled, appearance.stars != nil else { return .single(state) }
            return account.postbox.transaction { transaction in
                let ids = Set((appearance.starsHistory ?? []).compactMap { $0.peerId } + [account.peerId.toInt64()])
                var peers: [Int64: EnginePeer] = [:]
                for id in ids { if let peer = transaction.getPeer(EnginePeer.Id(id)) { peers[id] = EnginePeer(peer) } }
                var result = state
                result.transactions = VisualGramLocalAppearance.shared.starsHistoryTransactions(accountId: account.peerId, mode: self.visualGramMode, peers: peers)
                result.canLoadMore = false
                result.isLoading = false
                return result
            }
        }
    }

    private var visualGramServerState: Signal<StarsTransactionsContext.State, NoError> {
        return Signal { subscriber in''', 1)
    part = part.replace('    init(account: Account, subject: StarsTransactionsContext.Subject, mode: Mode) {\n', '    init(account: Account, subject: StarsTransactionsContext.Subject, mode: Mode) {\n        self.visualGramAccount = account\n        self.visualGramMode = mode\n', 1)
    if 'private var visualGramServerState' not in part:
        raise ValueError('Stars transactions context changed')
    stars.write_text(text[:start] + part + text[end:], encoding='utf-8')
    screen = root / 'submodules/TelegramUI/Components/Stars/StarsTransactionsScreen/Sources/StarsTransactionsScreen.swift'
    replace(screen, '                self.stateDisposable = (component.starsContext.state\n', '                self.stateDisposable = (combineLatest(component.starsContext.state, VisualGramLocalAppearance.shared.changes) |> map { state, _ in state }\n')
    replace(screen, '            let initialTransactions = self.starsState?.transactions ?? []\n', '''            let localWallet = VisualGramLocalAppearance.shared.appearance(accountId: component.context.account.peerId)
            let showLocalHistory = localWallet.enabled && localWallet.stars != nil && !component.starsContext.ton && component.starsContext.peerId == component.context.account.peerId
            let hasTransactions = showLocalHistory ? !(localWallet.starsHistory ?? []).isEmpty : !(self.starsState?.transactions ?? []).isEmpty
''')
    replace(screen, '            if !initialTransactions.isEmpty {\n', '            if hasTransactions {\n')

    shared = root / 'submodules/TelegramUI/Sources/SharedAccountContext.swift'
    text = shared.read_text(encoding='utf-8')
    start = text.index('        presentTransferAlertImpl = { [weak controller] peer in')
    tail = text[start:]
    needle = '                    if transferStars > 0, let starsContext = context.starsContext, let starsState = starsContext.currentState {\n'
    if tail.count(needle) != 1:
        raise ValueError('Transfer balance check changed')
    tail = tail.replace(needle, '''                    if case let .starGiftTransfer(_, reference, _, _, _, _) = source, VisualGramLocalAppearance.isLocalReference(reference) {
                        let wallet = VisualGramLocalAppearance.shared.appearance(accountId: context.account.peerId)
                        guard wallet.enabled, let balance = wallet.stars, balance >= VisualGramLocalAppearance.localGiftTransferStars else {
                            dismissAlertImpl?()
                            controller?.present(textAlertController(context: context, title: nil, text: "Недостаточно звёзд", actions: [TextAlertAction(type: .defaultAction, title: presentationData.strings.Common_OK, action: {})]), in: .window(.root))
                            return
                        }
                        proceed(false)
                        return
                    }
''' + needle, 1)
    shared.write_text(text[:start] + tail, encoding='utf-8')
    options = root / 'submodules/TelegramUI/Components/Gifts/GiftOptionsScreen/Sources/GiftOptionsScreen.swift'
    replace(options, '                        guard VisualGramLocalAppearance.shared.transferLocalGift(accountId: context.account.peerId, reference: reference, recipientPeerId: peer.id, now: Int32(clamping: Int64(Date().timeIntervalSince1970))) else {\n', '''                        let wallet = VisualGramLocalAppearance.shared.appearance(accountId: context.account.peerId)
                        guard wallet.enabled, let balance = wallet.stars, balance >= VisualGramLocalAppearance.localGiftTransferStars else {
                            dismissAlertImpl?()
                            mainController.present(textAlertController(context: context, title: nil, text: "Недостаточно звёзд", actions: [TextAlertAction(type: .defaultAction, title: presentationData.strings.Common_OK, action: {})]), in: .window(.root))
                            return
                        }
                        guard VisualGramLocalAppearance.shared.transferLocalGift(accountId: context.account.peerId, reference: reference, recipientPeerId: peer.id, now: Int32(clamping: Int64(Date().timeIntervalSince1970))) else {
''')
