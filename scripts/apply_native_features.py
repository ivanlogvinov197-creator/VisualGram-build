"""Apply local presentation hooks to the pinned Telegram source, failing on drift."""
import argparse
from pathlib import Path
import re
import shutil

from prepare_native import replace


def apply(root, project):
    shutil.copyfile(project / "native/VisualGramLogo.svg", root / "Telegram/Telegram-iOS/Telegram.icon/Assets/Plane.svg")
    core = root / "submodules/TelegramCore/Sources"
    peer = root / "submodules/TelegramUI/Components/PeerInfo/PeerInfoScreen"
    shutil.copyfile(project / "native/VisualGramLocalAppearance.swift", core / "VisualGramLocalAppearance.swift")
    shutil.copyfile(project / "native/VisualGramGiftManagement.swift", core / "VisualGramGiftManagement.swift")
    shutil.copyfile(project / "native/VisualGramGiftTrading.swift", core / "VisualGramGiftTrading.swift")
    shutil.copyfile(project / "native/VisualGramAppearanceController.swift", peer / "Sources/VisualGramAppearanceController.swift")
    shutil.copyfile(project / "native/VisualGramChatGifts.swift", root / "submodules/TelegramUI/Sources/VisualGramChatGifts.swift")
    shutil.copyfile(project / "native/VisualGramGiftDelivery.swift", root / "submodules/TelegramUI/Sources/VisualGramGiftDelivery.swift")
    account_context = root / "submodules/TelegramUI/Sources/AccountContext.swift"
    replace(account_context, '    private var experimentalUISettingsDisposable: Disposable?\n', '    private var experimentalUISettingsDisposable: Disposable?\n    private var visualGramGiftDelivery: VisualGramGiftDelivery?\n')
    replace(account_context, '            (self.animationRenderer as? DCTMultiAnimationRendererImpl)?.useYuvA = settings.compressedEmojiCache\n        })\n    }', '            (self.animationRenderer as? DCTMultiAnimationRendererImpl)?.useYuvA = settings.compressedEmojiCache\n        })\n        if !temp { self.visualGramGiftDelivery = VisualGramGiftDelivery(context: self) }\n    }')
    replace(account_context, '        self.experimentalUISettingsDisposable?.dispose()\n', '        self.experimentalUISettingsDisposable?.dispose()\n        self.visualGramGiftDelivery?.stop()\n')
    replace(peer / "BUILD", '    deps = [\n', '    deps = [\n        "//submodules/TelegramUI/Components/Gifts/GiftOptionsScreen",\n')

    data = peer / "Sources/PeerInfoData.swift"
    replace(data, '    let peer: EnginePeer?\n    let chatPeer:', '    let serverPeer: EnginePeer?\n    var peer: EnginePeer?\n    let chatPeer:')
    replace(data, '    let cachedData: CachedPeerData?\n    let status:', '    let serverCachedData: CachedPeerData?\n    var cachedData: CachedPeerData?\n    let status:')
    replace(data, '    let availablePanes: [PeerInfoPaneKey]\n', '    let serverAvailablePanes: [PeerInfoPaneKey]\n    var availablePanes: [PeerInfoPaneKey]\n')
    replace(data, '        self.peer = peer\n        self.chatPeer', '        self.serverPeer = peer\n        self.peer = peer\n        self.chatPeer')
    replace(data, '        self.cachedData = cachedData\n        self.status', '        self.serverCachedData = cachedData\n        self.cachedData = cachedData\n        self.status')
    replace(data, '        self.availablePanes = availablePanes\n', '        self.serverAvailablePanes = availablePanes\n        self.availablePanes = availablePanes\n')
    source = data.read_text(encoding="utf-8")
    signature = '    init(\n        peer: EnginePeer?,\n'
    start = source.index(signature)
    end = source.index('    ) {', start)
    parameters = re.findall(r'^        (\w+):', source[start:end], re.MULTILINE)
    if len(parameters) != 45:
        raise ValueError("PeerInfoScreenData constructor changed")
    original = {"peer": "serverPeer", "cachedData": "serverCachedData", "availablePanes": "serverAvailablePanes"}
    arguments = ',\n'.join(f'            {name}: self.{original.get(name, name)}' for name in parameters)
    copy = '    func visualGramCopy() -> PeerInfoScreenData {\n        return PeerInfoScreenData(\n' + arguments + '\n        )\n    }\n\n'
    replace(data, signature, copy + signature)

    screen = peer / "Sources/PeerInfoScreen.swift"
    replace(screen, '            screenData,\n            self.forceIsContactPromise.get(),', '''            combineLatest(screenData, VisualGramLocalAppearance.shared.changes)
            |> map { serverData, _ -> PeerInfoScreenData in
                let data = serverData.visualGramCopy()
                data.peer = VisualGramLocalAppearance.shared.displayPeer(data.serverPeer, accountId: context.account.peerId)
                data.cachedData = data.serverCachedData
                data.availablePanes = data.serverAvailablePanes
                let appearance = VisualGramLocalAppearance.shared.appearance(accountId: context.account.peerId, targetPeerId: peerId)
                if appearance.enabled {
                    if let verification = appearance.verification, let cached = data.serverCachedData as? CachedUserData {
                        data.cachedData = cached.withUpdatedVerification(verification)
                    }
                    if let rating = appearance.starRating, let cached = data.cachedData as? CachedUserData {
                        data.cachedData = cached.withUpdatedStarRating(rating).withUpdatedPendingStarRating(nil)
                    }
                    if appearance.gifts.contains(where: { $0.direction == .received }) && data.profileGiftsContext != nil && data.profileGiftsCollectionsContext != nil && !data.availablePanes.contains(.gifts) {
                        data.availablePanes.append(.gifts)
                    }
                }
                return data
            },
            self.forceIsContactPromise.get(),''')

    settings = peer / "Sources/PeerInfoSettingsItems.swift"
    # Appearance controls are opened by three consecutive taps on Chats.

    replace(settings, '    if let starsState = data.starsState {\n        if !isPremiumDisabled || abs(starsState.balance.value) > 0 {', '''    if var starsState = data.starsState {
        let appearance = VisualGramLocalAppearance.shared.appearance(accountId: context.account.peerId)
        if appearance.enabled, let balance = appearance.stars {
            starsState.balance = StarsAmount(value: balance, nanos: 0)
        }
        if !isPremiumDisabled || abs(starsState.balance.value) > 0 {''')

    stars = root / "submodules/TelegramUI/Components/Stars/StarsTransactionsScreen/Sources/StarsTransactionsScreen.swift"
    replace(core / "TelegramEngine/Payments/Stars.swift", '''    var peerId: EnginePeer.Id {
        var peerId: EnginePeer.Id?
        self.impl.syncWith { impl in
            peerId = impl.peerId
        }
        return peerId!
    }
    
    public let ton: Bool''', '''    public var peerId: EnginePeer.Id {
        var peerId: EnginePeer.Id?
        self.impl.syncWith { impl in
            peerId = impl.peerId
        }
        return peerId!
    }
    
    public let ton: Bool''')
    replace(stars, '            let formattedBalance: String\n', '''            let appearance = VisualGramLocalAppearance.shared.appearance(accountId: component.context.account.peerId)
            let displayStarsBalance: StarsAmount
            if appearance.enabled, !component.starsContext.ton, component.starsContext.peerId == component.context.account.peerId, let balance = appearance.stars {
                displayStarsBalance = StarsAmount(value: balance, nanos: 0)
            } else {
                displayStarsBalance = self.starsState?.balance ?? StarsAmount.zero
            }
            let formattedBalance: String
''')
    replace(stars, 'formattedBalance = formatStarsAmountText(self.starsState?.balance ?? StarsAmount.zero,', 'formattedBalance = formatStarsAmountText(displayStarsBalance,')
    replace(stars, 'count: self.starsState?.balance ?? StarsAmount.zero,', 'count: displayStarsBalance,')

    collectible = root / "submodules/TelegramUI/Components/Settings/CollectibleItemInfoScreen/Sources/CollectibleItemInfoScreen.swift"
    replace(collectible, '        case let .phoneNumber(phoneNumber):\n            return combineLatest(', '''        case let .phoneNumber(phoneNumber):
            let appearance = VisualGramLocalAppearance.shared.appearance(accountId: context.account.peerId, targetPeerId: peerId)
            if appearance.enabled, let local = appearance.phoneNumber, local.name.hasPrefix("888"), local.name == phoneNumber.filter({ $0.isNumber }) {
                return context.engine.data.get(TelegramEngine.EngineData.Item.Peer.Peer(id: peerId))
                |> map { peer -> CollectibleItemInfoScreenInitialData? in
                    return InitialData(peer: VisualGramLocalAppearance.shared.displayPeer(peer, accountId: context.account.peerId), subject: .phoneNumber(ResolvedSubject.PhoneNumber(phoneNumber: local.name, info: local.collectiblePhoneInfo)))
                }
            }
            return combineLatest(''')
    replace(collectible, '        case let .username(username):\n            return combineLatest(', '''        case let .username(username):
            if let local = VisualGramLocalAppearance.shared.localUsername(accountId: context.account.peerId, peerId: peerId, name: username) {
                return context.engine.data.get(TelegramEngine.EngineData.Item.Peer.Peer(id: peerId))
                |> map { peer -> CollectibleItemInfoScreenInitialData? in
                    return InitialData(peer: VisualGramLocalAppearance.shared.displayPeer(peer, accountId: context.account.peerId), subject: .username(ResolvedSubject.Username(username: username, info: local.collectibleInfo)))
                }
            }
            return combineLatest(''')

    gifts = core / "TelegramEngine/Payments/StarGifts.swift"
    replace(gifts, '    public var state: Signal<ProfileGiftsContext.State, NoError> {\n', '    private var serverState: Signal<ProfileGiftsContext.State, NoError> {\n')
    replace(gifts, '    public let peerId: EnginePeer.Id\n    public let collectionId: Int32?\n', '''    private let visualGramAccount: Account
    public var state: Signal<ProfileGiftsContext.State, NoError> {
        return combineLatest(self.serverState, VisualGramLocalAppearance.shared.changes)
        |> mapToSignal { state, _ -> Signal<ProfileGiftsContext.State, NoError> in
            let appearance = VisualGramLocalAppearance.shared.appearance(accountId: self.visualGramAccount.peerId, targetPeerId: self.peerId)
            guard appearance.enabled else {
                return .single(state)
            }
            return self.visualGramAccount.postbox.transaction { transaction in
                var senders: [Int64: EnginePeer] = [:]
                for gift in appearance.gifts {
                    if let id = gift.counterpartyId, let peer = transaction.getPeer(EnginePeer.Id(id)) { senders[id] = EnginePeer(peer) }
                }
                return VisualGramLocalAppearance.shared.profileState(state, accountId: self.visualGramAccount.peerId, peerId: self.peerId, collectionId: self.collectionId, senders: senders)
            }
        }
    }

    public let peerId: EnginePeer.Id
    public let collectionId: Int32?
''')
    replace(gifts, '        self.peerId = peerId\n        self.collectionId = collectionId\n        \n        let queue = self.queue', '        self.visualGramAccount = account\n        self.peerId = peerId\n        self.collectionId = collectionId\n        \n        let queue = self.queue')

    account = core / "TelegramEngine/AccountData/TelegramEngineAccountData.swift"
    replace(account, '        public func setEmojiStatus(file: TelegramMediaFile?, expirationDate: Int32?) -> Signal<Never, NoError> {\n', '''        public func setEmojiStatus(file: TelegramMediaFile?, expirationDate: Int32?) -> Signal<Never, NoError> {
            if VisualGramLocalAppearance.shared.setLocalEmojiStatus(accountId: self.account.peerId, status: file.map { PeerEmojiStatus(content: .emoji(fileId: $0.fileId.id), expirationDate: expirationDate) }) {
                return .complete()
            }
''')
    replace(account, '        public func setStarGiftStatus(starGift: StarGift.UniqueGift, expirationDate: Int32?) -> Signal<Never, NoError> {\n', '''        public func setStarGiftStatus(starGift: StarGift.UniqueGift, expirationDate: Int32?) -> Signal<Never, NoError> {
            if VisualGramLocalAppearance.shared.appearance(accountId: self.account.peerId).enabled {
                _ = VisualGramLocalAppearance.shared.setLocalGiftStatus(accountId: self.account.peerId, gift: starGift, expirationDate: expirationDate)
                return .complete()
            }
''')

    options = root / "submodules/TelegramUI/Components/Gifts/GiftOptionsScreen/Sources/GiftOptionsScreen.swift"
    replace(options, 'open class GiftOptionsScreen: ViewControllerComponentContainer, GiftOptionsScreenProtocol {\n', '''open class GiftOptionsScreen: ViewControllerComponentContainer, GiftOptionsScreenProtocol {
    public var visualGramGiftSelected: ((StarGift) -> Void)?
''')
    replace(options, '        private func openGift(gift: StarGift, skipDateCheck: Bool = false) {\n', '''        private func openGift(gift: StarGift, skipDateCheck: Bool = false) {
            if let controller = self.environment?.controller() as? GiftOptionsScreen, let select = controller.visualGramGiftSelected {
                select(gift)
                return
            }
''')

    gift_view = root / "submodules/TelegramUI/Components/Gifts/GiftViewScreen/Sources/GiftViewScreen.swift"
    replace(gift_view, 'component.context.isPremium', 'visualGramGiftHasPremium(context: component.context)', expected=2)
    with gift_view.open('a', encoding='utf-8', newline='\n') as output:
        output.write('''
private func visualGramGiftHasPremium(context: AccountContext) -> Bool {
    let appearance = VisualGramLocalAppearance.shared.appearance(accountId: context.account.peerId)
    return context.isPremium || (appearance.enabled && appearance.premium)
}
''')
    replace(gift_view, '                    .single(nil) |> then(context.engine.payments.cachedStarGifts())\n                ).startStrict(next: { [weak self] peers, starGifts in', '                    .single(nil) |> then(context.engine.payments.cachedStarGifts()),\n                    VisualGramLocalAppearance.shared.changes |> deliverOnMainQueue\n                ).startStrict(next: { [weak self] peers, starGifts, _ in')
    replace(gift_view, '                                peersMap[peerId] = peer\n', '                                peersMap[peerId] = VisualGramLocalAppearance.shared.displayPeer(peer, accountId: context.account.peerId) ?? peer\n')
    replace(gift_view, '        func updateSavedToProfile(_ added: Bool) {\n', '''        private var isVisualGramGift: Bool {
            if let controller = self.getController() as? GiftViewScreen, controller.customAction?.title.hasSuffix("локально") == true { return true }
            if case let .message(message) = self.subject, message.id.namespace == Int32.max - 42 { return true }
            if case let .profileGift(_, gift) = self.subject, gift.reference == nil || VisualGramLocalAppearance.isLocalReference(gift.reference) {
                return true
            }
            return false
        }

        func updateSavedToProfile(_ added: Bool) {
            if case let .profileGift(_, gift) = self.subject, VisualGramLocalAppearance.isLocalReference(gift.reference) {
                _ = VisualGramLocalAppearance.shared.updateGift(accountId: self.context.account.peerId, reference: gift.reference) { $0.savedToProfile = added; if !added { $0.pinnedToTop = false } }
                (self.getController() as? GiftViewScreen)?.dismissAnimated()
                return
            }
            guard !self.isVisualGramGift else { return }
''')
    for signature in [
        'convertToStars()', 'commitDropOriginalDetails()', 'sendGift(peerId: EnginePeer.Id)', 'shareGift()', 'setAsGiftTheme()',
        'craftGift()', 'transferGift()', 'resellGift(update: Bool = false)',
        'commitBuy(acceptedPrice: CurrencyAmount? = nil, skipConfirmation: Bool = false)',
        'commitUpgrade()', 'commitPrepaidUpgrade()', 'openGiftBuyOffer()',
        'commitGiftBuyOffer(peer: EnginePeer, price: CurrencyAmount, duration: Int32, allowPaidStars: Int64?)',
    ]:
        old = f'        func {signature} {{\n'
        replace(gift_view, old, old + '            guard !self.isVisualGramGift else { return }\n')
    replace(gift_view, '        func commitWear(_ uniqueGift: StarGift.UniqueGift) {\n', '''        func commitWear(_ uniqueGift: StarGift.UniqueGift) {
            if self.isVisualGramGift {
                VisualGramLocalAppearance.shared.update(accountId: self.context.account.peerId) { $0.enabled = true; $0.premium = true }
            }
''')
    replace(gift_view, '        func commitTakeOff() {\n', '''        func commitTakeOff() {
            if self.isVisualGramGift {
                VisualGramLocalAppearance.shared.update(accountId: self.context.account.peerId) { $0.enabled = true }
            }
''')

    history = root / "submodules/TelegramUI/Sources/ChatHistoryEntriesForView.swift"
    replace(history, '    if isMusicPlaylist && entries.count == 1 {\n', '''    if subject == nil, case let .peer(peerId) = location {
        let localEntries = visualGramChatGiftEntries(context: context, peerId: peerId, peer: chatPeer, view: view, presentationData: presentationData)
        if !localEntries.isEmpty {
            entries.append(contentsOf: localEntries)
            entries.sort()
        }
    }

    if isMusicPlaylist && entries.count == 1 {
''')
    history_node = root / "submodules/TelegramUI/Sources/ChatHistoryListNode.swift"
    replace(history_node, '        let historyViewUpdateValue = historyViewUpdate\n', '''        let visualGramServerHistory = historyViewUpdate
        historyViewUpdate = combineLatest(visualGramServerHistory, VisualGramLocalAppearance.shared.changes)
        |> map { value, _ in value }
        let historyViewUpdateValue = historyViewUpdate
''')
    context_menu = root / "submodules/TelegramUI/Sources/Chat/ChatControllerOpenMessageContextMenu.swift"
    signature = '    func openMessageContextMenu(message: EngineMessage, selectAll: Bool, node: ASDisplayNode, frame: CGRect, anyRecognizer: UIGestureRecognizer?, location: CGPoint?) -> Void {\n'
    replace(context_menu, signature, signature + '        guard message.id.namespace != Int32.max - 42 else { return }\n')
    controller = root / "submodules/TelegramUI/Sources/ChatController.swift"
    replace(controller, '        }, canSetupReply: { [weak self] message in\n', '        }, canSetupReply: { [weak self] message in\n            guard message.id.namespace != Int32.max - 42 else { return .none }\n')

    from apply_native_management import apply_management
    apply_management(root, project)
    from apply_native_shared import apply_shared
    apply_shared(root)
    from apply_native_upgrade import apply_upgrade
    apply_upgrade(root)
    from apply_native_trading import apply_trading
    apply_trading(root)
    from apply_native_revision import apply_revision
    apply_revision(root)
    from apply_native_gift_flow import apply_gift_flow
    apply_gift_flow(root, project)
    from apply_native_stars_history import apply_stars_history
    apply_stars_history(root, project)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    args = parser.parse_args()
    apply(args.source, Path(__file__).resolve().parent.parent)
    print("Local appearance hooks applied to official Telegram UI.")
