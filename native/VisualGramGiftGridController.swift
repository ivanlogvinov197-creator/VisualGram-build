import UIKit
import AsyncDisplayKit
import Display
import AccountContext
import TelegramCore
import TelegramPresentationData
import SwiftSignalKit
import ComponentFlow
import GiftItemComponent

private final class VisualGramGiftCell: UICollectionViewCell {
    private let component = ComponentView<Empty>()
    func update(context: AccountContext, gift: VisualGramGift, target: EnginePeer.Id, selected: Bool) {
        let data = context.sharedContext.currentPresentationData.with { $0 }
        let subject: GiftItemComponent.Subject
        switch gift.displayGift(accountId: target) {
        case let .unique(value): subject = .uniqueGift(gift: value, price: nil)
        case let .generic(value): subject = .starGift(gift: value, price: "")
        }
        let size = self.component.update(transition: .immediate, component: AnyComponent(GiftItemComponent(context: context, theme: data.theme, strings: data.strings, peer: nil, subject: subject, isHidden: gift.savedToProfile == false, isSelected: selected, isPinned: gift.pinnedToTop ?? false, isEditing: true, mode: .grid)), environment: {}, containerSize: self.contentView.bounds.size)
        if let view = self.component.view {
            if view.superview == nil { self.contentView.addSubview(view) }
            view.frame = CGRect(origin: .zero, size: size)
            view.isUserInteractionEnabled = false
        }
    }
}

final class VisualGramGiftGridController: ViewController, UICollectionViewDataSource, UICollectionViewDelegateFlowLayout, UICollectionViewDragDelegate, UICollectionViewDropDelegate {
    private let context: AccountContext
    private let target: EnginePeer.Id
    private let cardMode: Bool
    private let openGift: (String) -> Void
    private var items: [VisualGramGift] = []
    private var selected = Set<String>()
    private let grid: UICollectionView
    private let toolbar = UIStackView()
    private let help = UILabel()
    private var disposable: Disposable?

    init(context: AccountContext, target: EnginePeer.Id, cardMode: Bool = false, openGift: @escaping (String) -> Void) {
        self.context = context; self.target = target; self.cardMode = cardMode; self.openGift = openGift
        let layout = UICollectionViewFlowLayout(); layout.minimumInteritemSpacing = 8; layout.minimumLineSpacing = 8
        self.grid = UICollectionView(frame: .zero, collectionViewLayout: layout)
        super.init(navigationBarPresentationData: NavigationBarPresentationData(presentationData: context.sharedContext.currentPresentationData.with { $0 }))
        self.title = cardMode ? "Карточка GRAM" : "Подарки"
        self.navigationItem.rightBarButtonItem = UIBarButtonItem(title: "Открыть", style: .plain, target: self, action: #selector(self.openSelected))
    }
    required init(coder: NSCoder) { preconditionFailure() }
    deinit { self.disposable?.dispose() }

    override func loadDisplayNode() {
        self.displayNode = ASDisplayNode(); self.displayNodeDidLoad()
        let data = self.context.sharedContext.currentPresentationData.with { $0 }
        self.displayNode.backgroundColor = data.theme.list.blocksBackgroundColor
        self.grid.backgroundColor = .clear
        self.grid.register(VisualGramGiftCell.self, forCellWithReuseIdentifier: "gift")
        self.grid.dataSource = self; self.grid.delegate = self; self.grid.dragDelegate = self; self.grid.dropDelegate = self
        self.grid.dragInteractionEnabled = !self.cardMode
        self.view.addSubview(self.grid)
        self.help.font = .systemFont(ofSize: 13); self.help.textColor = data.theme.list.itemSecondaryTextColor; self.help.numberOfLines = 2
        self.help.text = self.cardMode ? "Выбери до 10 NFT для карточки. Один из них можно сделать фоном." : "Выбери подарки для действий. Удерживай и перетаскивай, чтобы изменить порядок."
        self.view.addSubview(self.help)
        self.toolbar.axis = .horizontal; self.toolbar.distribution = .fillEqually; self.toolbar.spacing = 8
        for (index, title) in (self.cardMode ? ["На карточку", "Фон", "Убрать"] : ["Показать", "Скрыть", "Закрепить", "Удалить"]).enumerated() {
            let button = UIButton(type: .system); button.setTitle(title, for: .normal); button.tag = index
            button.addTarget(self, action: #selector(self.performAction(_:)), for: .touchUpInside)
            self.toolbar.addArrangedSubview(button)
        }
        self.view.addSubview(self.toolbar)
        self.disposable = (VisualGramLocalAppearance.shared.changes |> deliverOnMainQueue).start(next: { [weak self] _ in self?.refresh() })
    }

    private func refresh() {
        let value = VisualGramLocalAppearance.shared.appearance(accountId: self.context.account.peerId, targetPeerId: self.target)
        self.items = value.gifts.filter { gift in
            guard gift.direction == .received, gift.isHistoryOnly != true else { return false }
            if self.cardMode { if case .unique = gift.gift { return true }; return false }
            return true
        }
        self.selected.formIntersection(Set(self.items.map { $0.identifier }))
        self.grid.reloadData()
        self.navigationItem.rightBarButtonItem?.isEnabled = self.selected.count == 1
    }

    override func containerLayoutUpdated(_ layout: ContainerViewLayout, transition: ContainedViewLayoutTransition) {
        super.containerLayoutUpdated(layout, transition: transition)
        let top = max(layout.safeInsets.top, layout.statusBarHeight ?? 0) + 52
        self.help.frame = CGRect(x: 16, y: top, width: layout.size.width - 32, height: 44)
        self.toolbar.frame = CGRect(x: 12, y: layout.size.height - layout.safeInsets.bottom - 60, width: layout.size.width - 24, height: 48)
        self.grid.frame = CGRect(x: 12, y: top + 52, width: layout.size.width - 24, height: max(0, self.toolbar.frame.minY - top - 60))
        self.grid.collectionViewLayout.invalidateLayout()
    }

    func collectionView(_ collectionView: UICollectionView, numberOfItemsInSection section: Int) -> Int { self.items.count }
    func collectionView(_ collectionView: UICollectionView, layout collectionViewLayout: UICollectionViewLayout, sizeForItemAt indexPath: IndexPath) -> CGSize {
        let width = floor((collectionView.bounds.width - 16) / 3)
        return CGSize(width: width, height: width * 1.32)
    }
    func collectionView(_ collectionView: UICollectionView, cellForItemAt indexPath: IndexPath) -> UICollectionViewCell {
        let cell = collectionView.dequeueReusableCell(withReuseIdentifier: "gift", for: indexPath)
        if let cell = cell as? VisualGramGiftCell { cell.update(context: self.context, gift: self.items[indexPath.item], target: self.target, selected: self.selected.contains(self.items[indexPath.item].identifier)) }
        return cell
    }
    func collectionView(_ collectionView: UICollectionView, didSelectItemAt indexPath: IndexPath) {
        let id = self.items[indexPath.item].identifier
        if !self.selected.insert(id).inserted { self.selected.remove(id) }
        self.grid.reloadItems(at: [indexPath]); self.navigationItem.rightBarButtonItem?.isEnabled = self.selected.count == 1
    }
    @objc private func openSelected() { if let id = self.selected.first, self.selected.count == 1 { self.openGift(id) } }
    @objc private func performAction(_ button: UIButton) {
        guard !self.selected.isEmpty else { return }
        if !self.cardMode && button.tag == 3 {
            let alert = UIAlertController(title: "Удалить выбранные подарки?", message: nil, preferredStyle: .alert)
            alert.addAction(UIAlertAction(title: "Отмена", style: .cancel))
            alert.addAction(UIAlertAction(title: "Удалить", style: .destructive, handler: { [weak self] _ in self?.saveAction(3) }))
            self.present(alert, animated: true); return
        }
        self.saveAction(button.tag)
    }
    private func saveAction(_ action: Int) {
        VisualGramLocalAppearance.shared.update(accountId: self.context.account.peerId, targetPeerId: self.target) { value in
            if self.cardMode {
                let ids = self.items.filter { self.selected.contains($0.identifier) }.map { $0.identifier }
                switch action {
                case 0: value.gramCardGiftIds = Array(((value.gramCardGiftIds ?? []).filter { !self.selected.contains($0) } + ids).suffix(10))
                case 1: if ids.count == 1 { value.gramCardGiftIds = [ids[0]] + (value.gramCardGiftIds ?? []).filter { $0 != ids[0] }.prefix(9); value.gramCardBackgroundId = ids[0] }
                default: value.gramCardGiftIds?.removeAll { self.selected.contains($0) }; if let id = value.gramCardBackgroundId, self.selected.contains(id) { value.gramCardBackgroundId = nil }
                }
            } else if action == 3 { value.gifts.removeAll { self.selected.contains($0.identifier) } }
            else {
                let alreadyPinned = value.gifts.filter { $0.pinnedToTop == true && !self.selected.contains($0.identifier) }.count
                guard action != 2 || alreadyPinned + self.selected.count <= 6 else { return }
                for index in value.gifts.indices where self.selected.contains(value.gifts[index].identifier) {
                    value.gifts[index].savedToProfile = action != 1
                    if action == 1 { value.gifts[index].pinnedToTop = false }
                    else if action == 2 { value.gifts[index].pinnedToTop = true }
                }
            }
        }
    }
    func collectionView(_ collectionView: UICollectionView, itemsForBeginning session: UIDragSession, at indexPath: IndexPath) -> [UIDragItem] {
        guard !self.cardMode else { return [] }
        let id = self.items[indexPath.item].identifier
        let item = UIDragItem(itemProvider: NSItemProvider(object: id as NSString)); item.localObject = id
        return [item]
    }
    func collectionView(_ collectionView: UICollectionView, dropSessionDidUpdate session: UIDropSession, withDestinationIndexPath destinationIndexPath: IndexPath?) -> UICollectionViewDropProposal {
        UICollectionViewDropProposal(operation: session.localDragSession != nil && !self.cardMode ? .move : .forbidden, intent: .insertAtDestinationIndexPath)
    }
    func collectionView(_ collectionView: UICollectionView, performDropWith coordinator: UICollectionViewDropCoordinator) {
        guard let item = coordinator.items.first, let id = item.dragItem.localObject as? String, let source = self.items.firstIndex(where: { $0.identifier == id }), !self.cardMode else { return }
        let destination = min(coordinator.destinationIndexPath?.item ?? self.items.count - 1, self.items.count - 1)
        let moved = self.items.remove(at: source); self.items.insert(moved, at: destination)
        let orderedIds = self.items.map { $0.identifier }
        VisualGramLocalAppearance.shared.update(accountId: self.context.account.peerId, targetPeerId: self.target) { value in
            let owned = value.gifts.filter { $0.direction == .received && $0.isHistoryOnly != true }
            guard Set(orderedIds).count == orderedIds.count, Set(orderedIds) == Set(owned.map { $0.identifier }), owned.count == orderedIds.count else { return }
            value.giftOrder = orderedIds
            let byId = Dictionary(uniqueKeysWithValues: owned.map { ($0.identifier, $0) })
            var index = 0
            value.gifts = value.gifts.map { gift in
                guard gift.direction == .received && gift.isHistoryOnly != true else { return gift }
                defer { index += 1 }; return byId[orderedIds[index]] ?? gift
            }
        }
        collectionView.reloadData(); coordinator.drop(item.dragItem, toItemAt: IndexPath(item: destination, section: 0))
    }
}
