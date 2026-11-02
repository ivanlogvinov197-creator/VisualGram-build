import UIKit
import AsyncDisplayKit
import Display
import AccountContext
import TelegramCore
import TelegramPresentationData
import SwiftSignalKit
import ComponentFlow
import GiftItemComponent
import WalletContext
import WalletCardComponent
import WalletGiftStickerMediaComponent

private final class VisualGramGiftCell: UICollectionViewCell {
    private let component = ComponentView<Empty>()
    private var parameters: (AccountContext, VisualGramGift, EnginePeer.Id, Bool, Bool)?
    private var renderedSize = CGSize.zero
    private var needsComponentUpdate = false
    func update(context: AccountContext, gift: VisualGramGift, target: EnginePeer.Id, selected: Bool, editing: Bool = false) {
        self.parameters = (context, gift, target, selected, editing)
        self.needsComponentUpdate = true
        self.updateComponent()
        self.setNeedsLayout()
    }
    override func layoutSubviews() {
        super.layoutSubviews()
        self.updateComponent()
    }
    private func updateComponent() {
        guard let (context, gift, target, selected, editing) = self.parameters,
              self.contentView.bounds.width > 0, self.contentView.bounds.height > 0,
              self.needsComponentUpdate || self.renderedSize != self.contentView.bounds.size else { return }
        self.needsComponentUpdate = false
        self.renderedSize = self.contentView.bounds.size
        let data = context.sharedContext.currentPresentationData.with { $0 }
        let subject: GiftItemComponent.Subject
        switch gift.displayGift(accountId: target) {
        case let .unique(value): subject = .uniqueGift(gift: value, price: nil)
        case let .generic(value): subject = .starGift(gift: value, price: "")
        }
        let size = self.component.update(transition: .immediate, component: AnyComponent(GiftItemComponent(context: context, theme: data.theme, strings: data.strings, peer: nil, subject: subject, isHidden: gift.savedToProfile == false, isSelected: selected, isPinned: gift.pinnedToTop ?? false, isEditing: editing, mode: .grid)), environment: {}, containerSize: self.contentView.bounds.size)
        if let view = self.component.view {
            if view.superview == nil { self.contentView.addSubview(view) }
            view.frame = CGRect(origin: .zero, size: size)
            view.isUserInteractionEnabled = false
        }
    }
}

final class VisualGramGiftGridController: ViewController, UICollectionViewDataSource, UICollectionViewDelegateFlowLayout {
    private let context: AccountContext
    private let target: EnginePeer.Id
    private let cardMode: Bool
    private let filterGift: ((VisualGramGift) -> Bool)?
    private let addGift: (() -> Void)?
    private var selecting = false
    private let openGift: (String) -> Void
    private var items: [VisualGramGift] = []
    private var selected = Set<String>()
    private let grid: UICollectionView
    private let giftActionsBar = UIStackView()
    private let help = UILabel()
    private var disposable: Disposable?

    init(context: AccountContext, target: EnginePeer.Id, cardMode: Bool = false, filterGift: ((VisualGramGift) -> Bool)? = nil, addGift: (() -> Void)? = nil, openGift: @escaping (String) -> Void) {
        self.filterGift = filterGift; self.addGift = addGift
        self.context = context; self.target = target; self.cardMode = cardMode; self.openGift = openGift
        let layout = UICollectionViewFlowLayout(); layout.minimumInteritemSpacing = 8; layout.minimumLineSpacing = 8
        self.grid = UICollectionView(frame: .zero, collectionViewLayout: layout)
        super.init(navigationBarPresentationData: NavigationBarPresentationData(presentationData: context.sharedContext.currentPresentationData.with { $0 }))
        self.title = cardMode ? "Выбери NFT" : "Подарки"
        self.updateNavigation()
    }
    required init(coder: NSCoder) { preconditionFailure() }
    deinit { self.disposable?.dispose() }

    override func loadDisplayNode() {
        self.displayNode = ASDisplayNode(); self.displayNodeDidLoad()
        let data = self.context.sharedContext.currentPresentationData.with { $0 }
        self.displayNode.backgroundColor = data.theme.list.blocksBackgroundColor
        self.grid.backgroundColor = .clear
        self.grid.register(VisualGramGiftCell.self, forCellWithReuseIdentifier: "gift")
        self.grid.dataSource = self; self.grid.delegate = self
        self.grid.dragInteractionEnabled = false
        self.view.addSubview(self.grid)
        self.help.font = .systemFont(ofSize: 13); self.help.textColor = data.theme.list.itemSecondaryTextColor; self.help.numberOfLines = 2
        self.help.text = self.cardMode ? "Выбери NFT." : "Нажми на подарок, чтобы открыть его. Порядок меняется отдельным списком."
        self.view.addSubview(self.help)
        self.giftActionsBar.axis = .horizontal; self.giftActionsBar.distribution = .fillEqually; self.giftActionsBar.spacing = 8
        for (index, title) in ["Показать", "Скрыть", "Закрепить", "Удалить"].enumerated() {
            let button = UIButton(type: .system); button.setTitle(title, for: .normal); button.tag = index
            button.addTarget(self, action: #selector(self.performAction(_:)), for: .touchUpInside)
            self.giftActionsBar.addArrangedSubview(button)
        }
        self.view.addSubview(self.giftActionsBar)
        self.giftActionsBar.isHidden = true
        self.disposable = (VisualGramLocalAppearance.shared.changes |> deliverOnMainQueue).start(next: { [weak self] _ in self?.refresh() })
    }

    private func refresh() {
        let value = VisualGramLocalAppearance.shared.appearance(accountId: self.context.account.peerId, targetPeerId: self.target)
        self.items = VisualGramLocalAppearance.orderedOwnedGifts(in: value).filter { gift in
            guard gift.direction == .received, gift.isHistoryOnly != true else { return false }
            if let filterGift = self.filterGift, !filterGift(gift) { return false }
            if self.cardMode { if case .unique = gift.gift { return true }; return false }
            return true
        }
        self.selected.formIntersection(Set(self.items.map { $0.identifier }))
        self.grid.reloadData()
        self.updateNavigation()
    }

    override func containerLayoutUpdated(_ layout: ContainerViewLayout, transition: ContainedViewLayoutTransition) {
        super.containerLayoutUpdated(layout, transition: transition)
        let top = max(layout.safeInsets.top, self.navigationLayout(layout: layout).navigationFrame.maxY)
        let left = layout.safeInsets.left + 12
        let width = max(0, layout.size.width - left - layout.safeInsets.right - 12)
        let bottom = max(layout.safeInsets.bottom, layout.intrinsicInsets.bottom)
        self.help.frame = CGRect(x: left + 4, y: top, width: max(0, width - 8), height: 44)
        self.giftActionsBar.frame = CGRect(x: left, y: layout.size.height - bottom - 60, width: width, height: 48)
        self.grid.frame = CGRect(x: left, y: top + 52, width: width, height: max(0, (self.giftActionsBar.isHidden ? layout.size.height - bottom : self.giftActionsBar.frame.minY) - top - 60))
        self.grid.collectionViewLayout.invalidateLayout()
    }

    func collectionView(_ collectionView: UICollectionView, numberOfItemsInSection section: Int) -> Int { self.items.count }
    func collectionView(_ collectionView: UICollectionView, layout collectionViewLayout: UICollectionViewLayout, sizeForItemAt indexPath: IndexPath) -> CGSize {
        let width = max(1, floor((collectionView.bounds.width - 16) / 3))
        return CGSize(width: width, height: width * 1.32)
    }
    func collectionView(_ collectionView: UICollectionView, cellForItemAt indexPath: IndexPath) -> UICollectionViewCell {
        let cell = collectionView.dequeueReusableCell(withReuseIdentifier: "gift", for: indexPath)
        if let cell = cell as? VisualGramGiftCell { cell.update(context: self.context, gift: self.items[indexPath.item], target: self.target, selected: self.selected.contains(self.items[indexPath.item].identifier), editing: self.selecting) }
        return cell
    }
    func collectionView(_ collectionView: UICollectionView, didSelectItemAt indexPath: IndexPath) {
        let id = self.items[indexPath.item].identifier
        if !self.selecting { self.openGift(id); return }
        if !self.selected.insert(id).inserted { self.selected.remove(id) }
        self.grid.reloadItems(at: [indexPath]); self.updateNavigation()
    }
    private func updateNavigation() {
        guard !self.cardMode else { self.navigationItem.rightBarButtonItems = []; return }
        var buttons = [UIBarButtonItem(title: self.selecting ? "Готово" : "Выбрать", style: .plain, target: self, action: #selector(self.toggleSelection)), UIBarButtonItem(title: "Порядок", style: .plain, target: self, action: #selector(self.reorder))]
        if self.addGift != nil { buttons.append(UIBarButtonItem(barButtonSystemItem: .add, target: self, action: #selector(self.add))) }
        self.navigationItem.rightBarButtonItems = buttons
    }
    @objc private func toggleSelection() {
        self.selecting.toggle(); self.selected.removeAll()
        self.giftActionsBar.isHidden = !self.selecting
        self.updateNavigation(); self.grid.reloadData(); self.requestLayout(transition: .immediate)
    }
    @objc private func reorder() { self.push(VisualGramGiftOrderController(context: self.context, target: self.target)) }
    @objc private func add() { self.addGift?() }
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
        if !self.cardMode && action == 3 {
            VisualGramLocalAppearance.shared.removeLocalGifts(accountId: self.context.account.peerId, targetPeerId: self.target, identifiers: self.selected)
            return
        }
        let configuration = self.context.currentAppConfiguration.with { $0 }
        let configuredLimit = configuration.data?["stargifts_pinned_to_top_limit"] as? Double ?? 6
        let pinLimit = configuredLimit.isFinite && configuredLimit >= 0 && configuredLimit < Double(Int.max) ? Int(configuredLimit) : 6
        var error: String?
        VisualGramLocalAppearance.shared.update(accountId: self.context.account.peerId, targetPeerId: self.target) { value in
            let owned = value.gifts.filter { $0.direction == .received && $0.isHistoryOnly != true }
            let selectedOwnedIds = Set(owned.filter { self.selected.contains($0.identifier) }.map { $0.identifier })
            guard !selectedOwnedIds.isEmpty else { error = "Список подарков изменился. Выбери подарок ещё раз."; return }
                let alreadyPinned = value.gifts.filter { $0.direction == .received && $0.isHistoryOnly != true && $0.pinnedToTop == true && !self.selected.contains($0.identifier) }.count
                guard action != 2 || alreadyPinned + selectedOwnedIds.count <= pinLimit else { error = "Можно закрепить до \(pinLimit) подарков."; return }
                for index in value.gifts.indices where selectedOwnedIds.contains(value.gifts[index].identifier) {
                    value.gifts[index].savedToProfile = action != 1
                    if action == 1 { value.gifts[index].pinnedToTop = false }
                    else if action == 2 { value.gifts[index].pinnedToTop = true }
                }
            
        }
        if let error {
            let alert = UIAlertController(title: nil, message: error, preferredStyle: .alert)
            alert.addAction(UIAlertAction(title: "OK", style: .default))
            self.present(alert, animated: true)
        }
    }
}

private final class VisualGramGiftOrderCell: UITableViewCell {
    let preview = VisualGramGiftCell(frame: .zero)
    override init(style: UITableViewCell.CellStyle, reuseIdentifier: String?) {
        super.init(style: .subtitle, reuseIdentifier: reuseIdentifier)
        self.contentView.addSubview(self.preview)
        self.preview.isUserInteractionEnabled = false
    }
    required init?(coder: NSCoder) { preconditionFailure() }
    override func layoutSubviews() {
        super.layoutSubviews()
        self.preview.frame = CGRect(x: 8, y: 4, width: 56, height: 72)
        self.textLabel?.frame.origin.x = 76
        self.detailTextLabel?.frame.origin.x = 76
        self.textLabel?.frame.size.width = max(0, self.contentView.bounds.width - 84)
        self.detailTextLabel?.frame.size.width = max(0, self.contentView.bounds.width - 84)
    }
}

private final class VisualGramGiftOrderController: ViewController, UITableViewDataSource, UITableViewDelegate {
    private let context: AccountContext
    private let target: EnginePeer.Id
    private var items: [VisualGramGift]
    private let table = UITableView(frame: .zero, style: .insetGrouped)
    init(context: AccountContext, target: EnginePeer.Id) {
        self.context = context; self.target = target
        self.items = VisualGramLocalAppearance.orderedOwnedGifts(in: VisualGramLocalAppearance.shared.appearance(accountId: context.account.peerId, targetPeerId: target))
        super.init(navigationBarPresentationData: NavigationBarPresentationData(presentationData: context.sharedContext.currentPresentationData.with { $0 }))
        self.title = "Порядок подарков"
        self.navigationItem.leftBarButtonItem = UIBarButtonItem(title: "Отмена", style: .plain, target: self, action: #selector(self.cancel))
        self.navigationItem.rightBarButtonItem = UIBarButtonItem(title: "Сохранить", style: .done, target: self, action: #selector(self.save))
    }
    required init(coder: NSCoder) { preconditionFailure() }
    override func loadDisplayNode() {
        self.displayNode = ASDisplayNode(); self.displayNodeDidLoad()
        let theme = self.context.sharedContext.currentPresentationData.with { $0 }.theme
        self.displayNode.backgroundColor = theme.list.blocksBackgroundColor
        self.table.backgroundColor = .clear; self.table.dataSource = self; self.table.delegate = self
        self.table.rowHeight = 80; self.table.allowsSelection = false
        self.table.register(VisualGramGiftOrderCell.self, forCellReuseIdentifier: "order")
        self.view.addSubview(self.table); self.table.setEditing(true, animated: false)
    }
    override func containerLayoutUpdated(_ layout: ContainerViewLayout, transition: ContainedViewLayoutTransition) {
        super.containerLayoutUpdated(layout, transition: transition)
        let top = self.navigationLayout(layout: layout).navigationFrame.maxY
        self.table.frame = CGRect(x: layout.safeInsets.left, y: top, width: max(0, layout.size.width - layout.safeInsets.left - layout.safeInsets.right), height: max(0, layout.size.height - top))
        self.table.contentInset.bottom = max(layout.intrinsicInsets.bottom, layout.safeInsets.bottom)
    }
    func tableView(_ tableView: UITableView, numberOfRowsInSection section: Int) -> Int { self.items.count }
    func tableView(_ tableView: UITableView, cellForRowAt indexPath: IndexPath) -> UITableViewCell {
        let cell = tableView.dequeueReusableCell(withIdentifier: "order", for: indexPath) as! VisualGramGiftOrderCell
        let gift = self.items[indexPath.row]
        let theme = self.context.sharedContext.currentPresentationData.with { $0 }.theme
        cell.backgroundColor = theme.list.itemBlocksBackgroundColor
        cell.textLabel?.textColor = theme.list.itemPrimaryTextColor
        cell.detailTextLabel?.textColor = theme.list.itemSecondaryTextColor
        switch gift.gift {
        case let .unique(value): cell.textLabel?.text = value.title; cell.detailTextLabel?.text = "#\(value.number)" + (gift.pinnedToTop == true ? " · Закреплён" : "")
        case let .generic(value): cell.textLabel?.text = value.title ?? "Подарок"; cell.detailTextLabel?.text = gift.pinnedToTop == true ? "Закреплён" : nil
        }
        cell.preview.update(context: self.context, gift: gift, target: self.target, selected: false)
        cell.showsReorderControl = true
        return cell
    }
    func tableView(_ tableView: UITableView, canMoveRowAt indexPath: IndexPath) -> Bool { true }
    func tableView(_ tableView: UITableView, editingStyleForRowAt indexPath: IndexPath) -> UITableViewCell.EditingStyle { .none }
    func tableView(_ tableView: UITableView, shouldIndentWhileEditingRowAt indexPath: IndexPath) -> Bool { false }
    func tableView(_ tableView: UITableView, targetIndexPathForMoveFromRowAt source: IndexPath, toProposedIndexPath proposed: IndexPath) -> IndexPath {
        let pinnedCount = self.items.filter { $0.pinnedToTop == true }.count
        let pinned = self.items[source.row].pinnedToTop == true
        return IndexPath(row: pinned ? min(proposed.row, max(0, pinnedCount - 1)) : max(proposed.row, pinnedCount), section: 0)
    }
    func tableView(_ tableView: UITableView, moveRowAt source: IndexPath, to destination: IndexPath) {
        let item = self.items.remove(at: source.row); self.items.insert(item, at: destination.row)
    }
    @objc private func cancel() { self.dismiss() }
    @objc private func save() {
        if VisualGramLocalAppearance.shared.saveGiftOrder(accountId: self.context.account.peerId, targetPeerId: self.target, identifiers: self.items.map { $0.identifier }) { self.dismiss(); return }
        let alert = UIAlertController(title: "Список изменился", message: "Подарок был добавлен или передан. Открой порядок заново, чтобы сохранить актуальный список.", preferredStyle: .alert)
        alert.addAction(UIAlertAction(title: "OK", style: .default))
        self.present(alert, animated: true)
    }
}

final class VisualGramCardEditorController: ViewController, UIGestureRecognizerDelegate {
    private let context: AccountContext
    private let target: EnginePeer.Id
    private var draft: VisualGramAppearance
    private let card = ComponentView<Empty>()
    private let buttons = UIStackView()
    private let help = UILabel()
    private var media: [String: WalletGiftStickerMedia] = [:]
    private var selected: String?
    private var renderedStickers: [WalletContext.CardSticker] = []
    private var lastLayout: ContainerViewLayout?
    private lazy var pan = UIPanGestureRecognizer(target: self, action: #selector(self.panSticker(_:)))
    private lazy var pinch = UIPinchGestureRecognizer(target: self, action: #selector(self.pinchSticker(_:)))
    private lazy var rotation = UIRotationGestureRecognizer(target: self, action: #selector(self.rotateSticker(_:)))
    private lazy var tap = UITapGestureRecognizer(target: self, action: #selector(self.selectSticker(_:)))

    init(context: AccountContext, target: EnginePeer.Id) {
        self.context = context; self.target = target
        self.draft = VisualGramLocalAppearance.shared.appearance(accountId: context.account.peerId, targetPeerId: target)
        super.init(navigationBarPresentationData: NavigationBarPresentationData(presentationData: context.sharedContext.currentPresentationData.with { $0 }))
        self.title = "Карточка GRAM"
        self.navigationItem.leftBarButtonItem = UIBarButtonItem(title: "Отмена", style: .plain, target: self, action: #selector(self.cancel))
        self.navigationItem.rightBarButtonItem = UIBarButtonItem(title: "Сохранить", style: .done, target: self, action: #selector(self.save))
        self.draft.enabled = true
        self.draft.grams = self.draft.grams ?? 0
        if let id = self.draft.gramCardBackgroundId, let local = self.draft.gifts.first(where: { $0.identifier == id }), case let .unique(gift) = local.gift, !WalletConfiguration.with(appConfiguration: context.currentAppConfiguration.with { $0 }).allowsCardBackground(giftSlug: gift.slug) { self.draft.gramCardBackgroundId = nil }
    }
    required init(coder: NSCoder) { preconditionFailure() }
    override func loadDisplayNode() {
        self.displayNode = ASDisplayNode(); self.displayNodeDidLoad()
        let theme = self.context.sharedContext.currentPresentationData.with { $0 }.theme
        self.displayNode.backgroundColor = theme.list.blocksBackgroundColor
        self.help.text = "Фон и наклейки выбираются отдельно. Перемещай наклейку одним пальцем, меняй размер и поворачивай двумя. Изменения сохранятся после подтверждения."
        self.help.numberOfLines = 0; self.help.font = .systemFont(ofSize: 15); self.help.textColor = theme.list.itemSecondaryTextColor
        self.view.addSubview(self.help)
        self.buttons.axis = .vertical; self.buttons.spacing = 12
        for (index, title) in ["Фон", "Добавить наклейку", "Убрать выбранную наклейку"].enumerated() {
            let button = UIButton(type: .system); button.setTitle(title, for: .normal); button.tag = index
            button.backgroundColor = theme.list.itemBlocksBackgroundColor; button.layer.cornerRadius = 12
            button.heightAnchor.constraint(equalToConstant: 48).isActive = true
            button.addTarget(self, action: #selector(self.action(_:)), for: .touchUpInside)
            self.buttons.addArrangedSubview(button)
        }
        self.view.addSubview(self.buttons)
        for gesture in [self.pan, self.pinch, self.rotation, self.tap] { gesture.delegate = self }
        self.pan.maximumNumberOfTouches = 2
    }
    override func containerLayoutUpdated(_ layout: ContainerViewLayout, transition: ContainedViewLayoutTransition) {
        super.containerLayoutUpdated(layout, transition: transition)
        self.lastLayout = layout; self.render()
    }
    private var cardView: WalletCardComponent.View? { self.card.view as? WalletCardComponent.View }
    private func render() {
        guard let layout = self.lastLayout else { return }
        let data = self.context.sharedContext.currentPresentationData.with { $0 }
        let left = layout.safeInsets.left + 16, width = max(0, layout.size.width - left - layout.safeInsets.right - 16)
        let top = self.navigationLayout(layout: layout).navigationFrame.maxY + 20
        let size = self.card.update(transition: .immediate, component: AnyComponent(WalletCardComponent(theme: data.theme, balance: self.draft.grams, fiatCurrency: .usd, fiatRate: nil, dateTimeFormat: data.dateTimeFormat, name: "", address: "", isVisible: true, qrPressed: {})), environment: {}, containerSize: CGSize(width: width, height: width * 220 / 370))
        guard let cardView = self.cardView else { return }
        cardView.stickerInteractionLocked = true
        if cardView.superview == nil { self.view.addSubview(cardView) }
        cardView.frame = CGRect(x: left, y: top, width: size.width, height: size.height)
        for gesture in [self.pan, self.pinch, self.rotation, self.tap] where gesture.view !== cardView { cardView.addGestureRecognizer(gesture) }
        let card = VisualGramLocalAppearance.shared.displayWalletCard(accountId: self.context.account.peerId, peerId: self.target, server: nil, appearanceOverride: self.draft)
        let stickers = (card?.stickers ?? []).compactMap { WalletContext.CardSticker(serverSticker: $0, backgroundNftAddress: card?.backgroundNft?.address) }
        self.renderedStickers = stickers
        let addresses = Set(stickers.map { $0.gift.address })
        for id in Array(self.media.keys) where !addresses.contains(id) { self.media.removeValue(forKey: id) }
        for sticker in stickers where self.media[sticker.gift.address] == nil {
            let media = WalletGiftStickerMedia(context: self.context, gift: sticker.gift, modelFile: sticker.modelFile, style: sticker.giftStyle)
            self.media[sticker.gift.address] = media
            media.updated = { [weak self] in self?.render() }
        }
        cardView.setCardStickers(stickers, images: self.media.compactMapValues { $0.first?.image }, hidden: [])
        let selectedGift = self.selected.flatMap { id in self.draft.gifts.first(where: { $0.identifier == id }) }
        let selectedAddress = selectedGift.flatMap { local -> String? in if case let .unique(gift) = local.gift { return "visualgram:" + gift.slug }; return nil }
        cardView.setStickerHint(stickers.first(where: { $0.gift.address == selectedAddress }), outline: nil)
        let background = stickers.last(where: { $0.style != nil })
        cardView.setGiftStyle(from: background?.style, to: background?.style, origin: .zero, progress: 1, pattern: background.flatMap { self.media[$0.gift.address]?.patternImage })
        self.help.frame = CGRect(x: left, y: cardView.frame.maxY + 20, width: width, height: 98)
        self.buttons.frame = CGRect(x: left, y: self.help.frame.maxY + 16, width: width, height: 168)
        self.buttons.arrangedSubviews.last?.isHidden = self.selected == nil
    }
    private func pick(background: Bool) {
        let config = WalletConfiguration.with(appConfiguration: self.context.currentAppConfiguration.with { $0 })
        let eligible: (VisualGramGift) -> Bool = { gift in
            guard case let .unique(value) = gift.gift else { return false }
            return !background || config.allowsCardBackground(giftSlug: value.slug)
        }
        guard self.draft.gifts.contains(where: { $0.direction == .received && $0.isHistoryOnly != true && eligible($0) }) else {
            self.message(background ? "Среди твоих NFT нет подарков, поддерживающих фон карточки." : "Сначала добавь NFT в профиль."); return
        }
        weak var pickerToDismiss: ViewController?
        let picker = VisualGramGiftGridController(context: self.context, target: self.target, cardMode: true, filterGift: eligible, openGift: { [weak self] id in
            guard let self else { return }
            let current = VisualGramLocalAppearance.shared.appearance(accountId: self.context.account.peerId, targetPeerId: self.target)
            guard let gift = current.gifts.first(where: { $0.identifier == id && $0.direction == .received && $0.isHistoryOnly != true }), eligible(gift) else { return }
            self.draft.gifts = current.gifts
            var ids = self.draft.gramCardGiftIds ?? []
            if !ids.contains(id) {
                guard ids.count < 10 else { self.message("На карточку можно добавить до 10 NFT."); return }
                ids.append(id)
            }
            self.draft.gramCardGiftIds = ids
            if self.draft.gramCardPlacements?[id] == nil {
                var positions = self.draft.gramCardPlacements ?? [:]; positions[id] = .init(x: 50, y: 64); self.draft.gramCardPlacements = positions
            }
            if background { self.draft.gramCardBackgroundId = id }
            self.selected = id; self.render(); self.settleSticker()
            pickerToDismiss?.dismiss()
        })
        pickerToDismiss = picker
        self.push(picker)
    }
    @objc private func action(_ button: UIButton) {
        switch button.tag {
        case 0:
            let alert = UIAlertController(title: "Фон карточки", message: nil, preferredStyle: .alert)
            alert.addAction(UIAlertAction(title: "Выбрать NFT", style: .default, handler: { [weak self] _ in self?.pick(background: true) }))
            alert.addAction(UIAlertAction(title: "Сбросить фон", style: .destructive, handler: { [weak self] _ in self?.draft.gramCardBackgroundId = nil; self?.render() }))
            alert.addAction(UIAlertAction(title: "Отмена", style: .cancel)); self.present(alert, animated: true)
        case 1: self.pick(background: false)
        default:
            guard let id = self.selected else { return }
            self.draft.gramCardGiftIds?.removeAll { $0 == id }; self.draft.gramCardPlacements?.removeValue(forKey: id)
            if self.draft.gramCardBackgroundId == id { self.draft.gramCardBackgroundId = nil }
            self.selected = nil; self.render()
        }
    }
    private func hit(_ gesture: UIGestureRecognizer) -> String? {
        guard let view = self.cardView, let sticker = view.sticker(at: gesture.location(in: view.stickerSurface)) else { return nil }
        return self.draft.gifts.first(where: { gift in
            if case let .unique(value) = gift.gift { return "visualgram:" + value.slug == sticker.gift.address }; return false
        })?.identifier
    }
    func gestureRecognizerShouldBegin(_ gestureRecognizer: UIGestureRecognizer) -> Bool {
        if gestureRecognizer === self.pan || gestureRecognizer === self.tap {
            self.selected = self.hit(gestureRecognizer)
            return self.selected != nil
        }
        if self.selected == nil { self.selected = self.hit(gestureRecognizer) }
        return self.selected != nil
    }
    func gestureRecognizer(_ gestureRecognizer: UIGestureRecognizer, shouldRecognizeSimultaneouslyWith otherGestureRecognizer: UIGestureRecognizer) -> Bool {
        let gestures: [UIGestureRecognizer] = [self.pan, self.pinch, self.rotation]
        return gestures.contains(where: { $0 === gestureRecognizer }) && gestures.contains(where: { $0 === otherGestureRecognizer })
    }
    private func modify(_ change: (inout VisualGramGift.CardPlacement) -> Void) {
        guard let id = self.selected, let index = self.draft.gramCardGiftIds?.firstIndex(of: id) else { return }
        var positions = self.draft.gramCardPlacements ?? [:]
        var value = positions[id] ?? .init(x: 20 + Double(index % 4) * 20, y: 74 - Double(index / 4) * 24)
        change(&value); positions[id] = value.normalized; self.draft.gramCardPlacements = positions; self.render()
    }
    private func settleSticker() {
        guard let id = self.selected, let view = self.cardView,
              let value = self.draft.gramCardPlacements?[id] else { return }
        let address = self.draft.gifts.first(where: { $0.identifier == id }).flatMap { local -> String? in if case let .unique(gift) = local.gift { return "visualgram:" + gift.slug }; return nil }
        let solver = WalletStickerPlacement(size: view.stickerSurface.bounds.size, obstacles: view.stickerObstacles, occupants: self.renderedStickers.filter { $0.gift.address != address })
        let aim = CGPoint(x: CGFloat(value.x / 100) * solver.size.width, y: CGFloat(value.y / 100) * solver.size.height)
        if let spot = solver.drop(near: aim, scale: CGFloat(value.scale)) {
            self.modify { $0.x = Double(spot.center.x / solver.size.width) * 100; $0.y = Double(spot.center.y / solver.size.height) * 100; $0.scale = Double(spot.scale) }
        }
    }
    @objc private func selectSticker(_ gesture: UITapGestureRecognizer) { self.selected = self.hit(gesture); self.render() }
    @objc private func panSticker(_ gesture: UIPanGestureRecognizer) {
        guard let surface = self.cardView?.stickerSurface, surface.bounds.width > 0, surface.bounds.height > 0 else { return }
        let delta = gesture.translation(in: surface); gesture.setTranslation(.zero, in: surface)
        self.modify { $0.x += Double(delta.x / surface.bounds.width) * 100; $0.y += Double(delta.y / surface.bounds.height) * 100 }
        if gesture.state == .ended { self.settleSticker() }
    }
    @objc private func pinchSticker(_ gesture: UIPinchGestureRecognizer) { let scale = Double(gesture.scale); gesture.scale = 1; self.modify { $0.scale *= scale }; if gesture.state == .ended && self.rotation.state != .changed { self.settleSticker() } }
    @objc private func rotateSticker(_ gesture: UIRotationGestureRecognizer) { let angle = Double(gesture.rotation) * 180 / .pi; gesture.rotation = 0; self.modify { $0.angle += angle }; if gesture.state == .ended && self.pinch.state != .changed { self.settleSticker() } }
    @objc private func cancel() { self.dismiss() }
    @objc private func save() {
        var saved = false
        VisualGramLocalAppearance.shared.update(accountId: self.context.account.peerId, targetPeerId: self.target) { value in
            let owned = Set(value.gifts.filter { $0.direction == .received && $0.isHistoryOnly != true }.map { $0.identifier })
            let ids = self.draft.gramCardGiftIds ?? []
            guard ids.count <= 10, Set(ids).count == ids.count, Set(ids).isSubset(of: owned) else { return }
            value.enabled = true; value.grams = value.grams ?? 0
            value.gramCardGiftIds = ids; value.gramCardBackgroundId = self.draft.gramCardBackgroundId
            value.gramCardPlacements = self.draft.gramCardPlacements?.filter { owned.contains($0.key) }; saved = true
        }
        if saved { self.dismiss() } else { self.message("Список подарков изменился. Открой оформление карточки заново.") }
    }
    private func message(_ text: String) {
        let alert = UIAlertController(title: nil, message: text, preferredStyle: .alert)
        alert.addAction(UIAlertAction(title: "OK", style: .default)); self.present(alert, animated: true)
    }
}
