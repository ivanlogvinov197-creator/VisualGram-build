"""Connect native gift controls to local state and reject local references at RPC boundary."""
from pathlib import Path
from prepare_native import replace


def apply_management(root: Path, project: Path):
    gifts = root / "submodules/TelegramCore/Sources/TelegramEngine/Payments/StarGifts.swift"
    replace(gifts, '    func apiStarGiftReference(transaction: Transaction) -> Api.InputSavedStarGift? {\n', '    func apiStarGiftReference(transaction: Transaction) -> Api.InputSavedStarGift? {\n        guard !VisualGramLocalAppearance.isLocalReference(self) else { return nil }\n')
    replace(gifts, '    func loadMore(reload: Bool = false) {\n        let peerId = self.peerId\n        let collectionId = self.collectionId\n', '''    func loadMore(reload: Bool = false) {
        if let collectionId = self.collectionId, collectionId < 0 {
            self.dataState = .ready(canLoadMore: false, nextOffset: nil)
            self.filteredDataState = .ready(canLoadMore: false, nextOffset: nil)
            self.count = 0
            self.filteredCount = 0
            self.pushState()
            return
        }
        let peerId = self.peerId
        let collectionId = self.collectionId
''')
    replace(gifts, '        return state\n    }\n}\n\n// MARK: - CraftGiftsContext', '''        return state.map { VisualGramLocalAppearance.shared.profileState($0, accountId: self.visualGramAccount.peerId, peerId: self.peerId, collectionId: self.collectionId) }
    }
}

// MARK: - CraftGiftsContext''')
    controls = {
        'updateStarGiftAddedToProfile(reference: StarGiftReference, added: Bool)': '''        if VisualGramLocalAppearance.isLocalReference(reference) {
            _ = VisualGramLocalAppearance.shared.updateGift(accountId: self.visualGramAccount.peerId, reference: reference) { $0.savedToProfile = added; if !added { $0.pinnedToTop = false } }
            return
        }
''',
        'updateStarGiftPinnedToTop(reference: StarGiftReference, pinnedToTop: Bool)': '''        if VisualGramLocalAppearance.isLocalReference(reference) {
            _ = VisualGramLocalAppearance.shared.updateGift(accountId: self.visualGramAccount.peerId, reference: reference) { $0.pinnedToTop = pinnedToTop; if pinnedToTop { $0.savedToProfile = true } }
            return
        }
''',
        'updatePinnedToTopStarGifts(references: [StarGiftReference])': '''        if references.contains(where: { VisualGramLocalAppearance.isLocalReference($0) }) {
            VisualGramLocalAppearance.shared.reorderGifts(accountId: self.visualGramAccount.peerId, targetPeerId: self.peerId, references: references, updatePins: true)
            return
        }
''',
        'reorderStarGifts(references: [StarGiftReference])': '''        if references.contains(where: { VisualGramLocalAppearance.isLocalReference($0) }) {
            VisualGramLocalAppearance.shared.reorderGifts(accountId: self.visualGramAccount.peerId, targetPeerId: self.peerId, references: references)
            return
        }
''',
        'removeStarGifts(references: [StarGiftReference])': '''        if references.contains(where: { VisualGramLocalAppearance.isLocalReference($0) }) {
            VisualGramLocalAppearance.shared.update(accountId: self.visualGramAccount.peerId, targetPeerId: self.peerId) { value in value.gifts.removeAll { references.contains($0.reference(accountId: self.peerId)) } }
            return
        }
''',
    }
    for signature, body in controls.items():
        old = f'    public func {signature} {{\n        self.impl.with'
        replace(gifts, old, f'    public func {signature} {{\n' + body + '        self.impl.with')
    signature = 'func _internal_updateStarGiftsPinnedToTop(account: Account, peerId: EnginePeer.Id, references: [StarGiftReference]) -> Signal<Never, NoError> {\n'
    replace(gifts, signature, signature + '    guard !references.contains(where: { VisualGramLocalAppearance.isLocalReference($0) }) else { return .complete() }\n')
    signature = 'func _internal_craftStarGift(account: Account, references: [StarGiftReference]) -> Signal<ProfileGiftsContext.State.StarGift, CraftStarGiftError> {\n'
    replace(gifts, signature, signature + '    guard !references.contains(where: { VisualGramLocalAppearance.isLocalReference($0) }) else { return .fail(.generic) }\n')

    collections = root / "submodules/TelegramCore/Sources/TelegramEngine/Payments/StarGiftsCollections.swift"
    signature = 'private func _internal_createStarGiftCollection(account: Account, peerId: EnginePeer.Id, title: String, starGifts: [ProfileGiftsContext.State.StarGift]) -> Signal<StarGiftCollection?, NoError> {\n'
    replace(collections, signature, signature + '    guard !starGifts.contains(where: { VisualGramLocalAppearance.isLocalReference($0.reference) }) else { return .single(nil) }\n')
    signature = 'private func _internal_reorderStarGiftCollections(account: Account, peerId: EnginePeer.Id, order: [Int32]) -> Signal<Bool, NoError> {\n'
    replace(collections, signature, signature + '    guard !order.contains(where: { $0 < 0 }) else { return .single(false) }\n')
    signature = 'private func _internal_deleteStarGiftCollection(account: Account, peerId: EnginePeer.Id, collectionId: Int32) -> Signal<Bool, NoError> {\n'
    replace(collections, signature, signature + '    guard collectionId >= 0 else { return .single(false) }\n')
    signature = 'private func _internal_updateStarGiftCollection(account: Account, peerId: EnginePeer.Id, collectionId: Int32, giftsContext: ProfileGiftsContext?, allGiftsContext: ProfileGiftsContext?, actions: [ProfileGiftsCollectionsContext.UpdateAction]) -> Signal<StarGiftCollection?, NoError> {\n'
    replace(collections, signature, signature + '''    guard collectionId >= 0, !actions.contains(where: { action in
        switch action {
        case let .addGifts(gifts): return gifts.contains { VisualGramLocalAppearance.isLocalReference($0.reference) }
        case let .removeGifts(refs), let .reorderGifts(refs): return refs.contains { VisualGramLocalAppearance.isLocalReference($0) }
        case .updateTitle: return false
        }
    }) else { return .single(nil) }
''')
    replace(collections, '    public var state: Signal<State, NoError> {\n        return self.stateValue.get()\n    }', '''    public var state: Signal<State, NoError> {
        return combineLatest(self.stateValue.get(), VisualGramLocalAppearance.shared.changes)
        |> map { state, _ in VisualGramLocalAppearance.shared.collectionsState(state, accountId: self.account.peerId, peerId: self.peerId) }
    }''')
    signature = '    public func createCollection(title: String, starGifts: [ProfileGiftsContext.State.StarGift]) -> Signal<StarGiftCollection?, NoError> {\n'
    replace(collections, signature, signature + '''        if VisualGramLocalAppearance.shared.appearance(accountId: self.account.peerId, targetPeerId: self.peerId).enabled {
            return .single(VisualGramLocalAppearance.shared.createCollection(accountId: self.account.peerId, targetPeerId: self.peerId, title: title, references: starGifts.compactMap { $0.reference }))
        }
        if starGifts.contains(where: { VisualGramLocalAppearance.isLocalReference($0.reference) }) { return .single(nil) }
''')
    signature = '    public func updateCollection(id: Int32, actions: [UpdateAction]) -> Signal<StarGiftCollection?, NoError> {\n'
    replace(collections, signature, signature + '''        let hasLocal = id < 0 || actions.contains { action in
            switch action {
            case let .addGifts(gifts): return gifts.contains { VisualGramLocalAppearance.isLocalReference($0.reference) }
            case let .removeGifts(refs), let .reorderGifts(refs): return refs.contains { VisualGramLocalAppearance.isLocalReference($0) }
            case .updateTitle: return false
            }
        }
        if hasLocal {
            VisualGramLocalAppearance.shared.updateCollection(accountId: self.account.peerId, targetPeerId: self.peerId, id: id, actions: actions)
            return .single(VisualGramLocalAppearance.shared.collection(accountId: self.account.peerId, targetPeerId: self.peerId, id: id))
        }
''')
    signature = '    public func reorderCollections(order: [Int32]) -> Signal<Bool, NoError> {\n'
    replace(collections, signature, signature + '''        if order.contains(where: { $0 < 0 }) {
            VisualGramLocalAppearance.shared.update(accountId: self.account.peerId, targetPeerId: self.peerId) { value in
                let current = value.collections ?? []
                value.collections = order.compactMap { id in current.first { $0.id == id } } + current.filter { !order.contains($0.id) }
            }
            return .single(true)
        }
''')
    signature = '    public func deleteCollection(id: Int32) -> Signal<Bool, NoError> {\n'
    replace(collections, signature, signature + '''        if id < 0 {
            VisualGramLocalAppearance.shared.update(accountId: self.account.peerId, targetPeerId: self.peerId) { value in
                value.collections?.removeAll { $0.id == id }
                for index in value.gifts.indices { value.gifts[index].collectionIds?.removeAll { $0 == id } }
            }
            return .single(true)
        }
''')
    pane = root / "submodules/TelegramUI/Components/PeerInfo/PeerInfoVisualMediaPaneNode/Sources/PeerInfoGiftsPaneNode.swift"
    replace(pane, '        let canManage = self.peerId == self.context.account.peerId || self.canManage\n', '        let canManage = self.peerId == self.context.account.peerId || self.canManage || VisualGramLocalAppearance.isLocalReference(gift.reference)\n')
    replace(pane, '            if case let .unique(uniqueGift) = gift.gift, self.peerId == self.context.account.peerId {\n', '            if case let .unique(uniqueGift) = gift.gift, self.peerId == self.context.account.peerId || VisualGramLocalAppearance.isLocalReference(gift.reference) {\n')
    replace(pane, '                        if self.context.isPremium {\n                            let _ = self.context.engine.accountData.setStarGiftStatus(starGift: uniqueGift, expirationDate: nil).startStandalone()\n', '''                        if VisualGramLocalAppearance.isLocalReference(gift.reference) {
                            VisualGramLocalAppearance.shared.update(accountId: self.context.account.peerId, targetPeerId: self.peerId) { $0.enabled = true; $0.premium = true }
                            _ = VisualGramLocalAppearance.shared.setLocalGiftStatus(accountId: self.context.account.peerId, targetPeerId: self.peerId, gift: uniqueGift, expirationDate: nil)
                            return
                        }
                        if self.context.isPremium {
                            let _ = self.context.engine.accountData.setStarGiftStatus(starGift: uniqueGift, expirationDate: nil).startStandalone()
''')
