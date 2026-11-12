import UIKit
import AsyncDisplayKit
import AccountContext
import AppBundle
import AttachmentUI
import AvatarComponent
import ComponentFlow
import Display
import PresentationDataUtils
import SwiftSignalKit
import TelegramCore
import TelegramPresentationData
import TelegramStringFormatting
import WalletCardComponent
import WalletContext
import WalletGiftStickerMediaComponent

private func gramAmount(_ amount: Int64, data: PresentationData) -> String {
    formatTonAmountText(amount, dateTimeFormat: data.dateTimeFormat, maxDecimalPositions: 9, formatString: data.strings.Currency_Grams)
}

private func gramLabel(_ text: String, font: UIFont, color: UIColor) -> UILabel {
    let label = UILabel()
    label.text = text
    label.font = font
    label.textColor = color
    return label
}

private func gramButton(_ title: String, theme: PresentationTheme, action: @escaping () -> Void) -> UIButton {
    let button = UIButton(type: .system)
    button.setTitle(title, for: .normal)
    button.setTitleColor(theme.list.itemCheckColors.foregroundColor, for: .normal)
    button.backgroundColor = theme.list.itemCheckColors.fillColor
    button.layer.cornerRadius = 23
    button.titleLabel?.font = .systemFont(ofSize: 17, weight: .semibold)
    button.heightAnchor.constraint(equalToConstant: 46).isActive = true
    button.addAction(UIAction { _ in action() }, for: .touchUpInside)
    return button
}

private func presentGramTopUp(on controller: ViewController, context: AccountContext, data: PresentationData) {
    let alert = UIAlertController(title: "Пополнить локальный баланс", message: nil, preferredStyle: .alert)
    alert.overrideUserInterfaceStyle = data.theme.overallDarkAppearance ? .dark : .light
    alert.addTextField { field in
        field.keyboardType = .decimalPad
        field.keyboardAppearance = data.theme.overallDarkAppearance ? .dark : .light
        field.placeholder = "Сумма GRAM"
    }
    alert.addAction(UIAlertAction(title: data.strings.Common_Cancel, style: .cancel))
    alert.addAction(UIAlertAction(title: "Пополнить", style: .default, handler: { [weak controller, weak alert] _ in
        guard let controller else { return }
        let amount = VisualGramLocalAppearance.parseGrams(alert?.textFields?.first?.text ?? "") ?? 0
        if !VisualGramLocalAppearance.shared.topUpLocalGrams(accountId: context.account.peerId, amount: amount, now: Int32(clamping: Int64(Date().timeIntervalSince1970))) {
            controller.present(textAlertController(context: context, title: nil, text: "Проверьте сумму пополнения.", actions: [TextAlertAction(type: .defaultAction, title: data.strings.Common_OK, action: {})]), in: .window(.root))
        }
    }))
    var presenter = controller.view.window?.rootViewController
    while let presented = presenter?.presentedViewController { presenter = presented }
    presenter?.present(alert, animated: true)
}

public final class VisualGramSendMoneyScreen: ViewController, AttachmentContainable {
    public var requestAttachmentMenuExpansion: () -> Void = {}
    public var updateNavigationStack: (@escaping ([AttachmentContainable]) -> ([AttachmentContainable], AttachmentMediaPickerContext?)) -> Void = { _ in }
    public var parentController: () -> ViewController? = { nil }
    public var updateTabBarAlpha: (CGFloat, ContainedViewLayoutTransition) -> Void = { _, _ in }
    public var updateTabBarVisibility: (Bool, ContainedViewLayoutTransition) -> Void = { _, _ in }
    public var cancelPanGesture: () -> Void = {}
    public var isContainerPanning: () -> Bool = { false }
    public var isContainerExpanded: () -> Bool = { false }
    public var mediaPickerContext: AttachmentMediaPickerContext? { nil }
    public var isMinimized = false
    public var allowsCollapsing: Bool { !self.amount.isFirstResponder && !self.comment.isFirstResponder }

    private let context: AccountContext
    private let peer: EnginePeer
    private let data: PresentationData
    private let dismissAttachment: (() -> Void)?
    private let completed: () -> Void
    private let scroll = UIScrollView()
    private let stack = UIStackView()
    private let avatar = ComponentView<Empty>()
    private let amount = UITextField()
    private let comment = UITextField()
    private let balance = UILabel()
    private var sendButton: UIButton?
    private var disposable: Disposable?
    private var confirming = false
    private var sent = false

    public init(context: AccountContext, peer: EnginePeer, dismissAttachment: (() -> Void)? = nil, completed: @escaping () -> Void = {}) {
        self.context = context
        self.peer = peer
        self.data = context.sharedContext.currentPresentationData.with { $0 }
        self.dismissAttachment = dismissAttachment
        self.completed = completed
        super.init(navigationBarPresentationData: nil)
        self.navigationPresentation = .modal
    }

    required public init(coder: NSCoder) { preconditionFailure() }
    deinit { self.disposable?.dispose() }

    override public func loadDisplayNode() {
        self.displayNode = ASDisplayNode()
        self.displayNodeDidLoad()
        let theme = self.data.theme
        self.view.overrideUserInterfaceStyle = theme.overallDarkAppearance ? .dark : .light
        self.displayNode.backgroundColor = theme.list.blocksBackgroundColor
        self.scroll.keyboardDismissMode = .interactive
        self.view.addSubview(self.scroll)
        self.stack.axis = .vertical
        self.stack.spacing = 14
        self.scroll.addSubview(self.stack)

        let heading = gramLabel(self.data.strings.Wallet_SendMoney, font: .systemFont(ofSize: 18, weight: .bold), color: theme.list.itemPrimaryTextColor)
        heading.textAlignment = .center
        let close = UIButton(type: .system)
        close.setImage(UIImage(systemName: "xmark.circle.fill"), for: .normal)
        close.tintColor = theme.list.itemAccentColor
        close.accessibilityLabel = self.data.strings.Common_Close
        close.widthAnchor.constraint(equalToConstant: 44).isActive = true
        close.addAction(UIAction { [weak self] _ in self?.close() }, for: .touchUpInside)
        let trailing = UIButton(type: .system)
        trailing.setImage(UIImage(systemName: "ellipsis.circle"), for: .normal)
        trailing.tintColor = theme.list.itemAccentColor
        trailing.accessibilityLabel = self.data.strings.Common_More
        trailing.widthAnchor.constraint(equalToConstant: 44).isActive = true
        trailing.menu = UIMenu(children: [
            UIAction(title: "Пополнить баланс", image: UIImage(systemName: "plus.circle")) { [weak self] _ in
                guard let self else { return }
                presentGramTopUp(on: self, context: self.context, data: self.data)
            },
            UIAction(title: "Добавить комментарий", image: UIImage(systemName: "bubble")) { [weak self] _ in
                guard let self else { return }
                self.comment.isHidden = false
                self.requestLayout(transition: .immediate)
                self.comment.becomeFirstResponder()
            }
        ])
        trailing.showsMenuAsPrimaryAction = true
        let header = UIStackView(arrangedSubviews: [close, heading, trailing])
        header.heightAnchor.constraint(equalToConstant: 44).isActive = true
        self.stack.addArrangedSubview(header)

        let recipient = gramLabel(self.peer.compactDisplayTitle, font: .systemFont(ofSize: 17, weight: .semibold), color: theme.list.itemPrimaryTextColor)
        let recipientRow = UIStackView()
        recipientRow.spacing = 10
        recipientRow.alignment = .center
        recipientRow.isLayoutMarginsRelativeArrangement = true
        recipientRow.layoutMargins = UIEdgeInsets(top: 0, left: 12, bottom: 0, right: 12)
        recipientRow.backgroundColor = theme.list.itemBlocksBackgroundColor
        recipientRow.layer.cornerRadius = 16
        recipientRow.heightAnchor.constraint(equalToConstant: 52).isActive = true
        let avatarSize = CGSize(width: 34, height: 34)
        _ = self.avatar.update(transition: .immediate, component: AnyComponent(AvatarComponent(context: self.context, theme: theme, peer: self.peer, size: avatarSize)), environment: {}, containerSize: avatarSize)
        if let view = self.avatar.view {
            recipientRow.addArrangedSubview(view)
            view.widthAnchor.constraint(equalToConstant: avatarSize.width).isActive = true
            view.heightAnchor.constraint(equalToConstant: avatarSize.height).isActive = true
        }
        recipientRow.addArrangedSubview(recipient)
        self.stack.addArrangedSubview(recipientRow)

        let notice = gramLabel("Локальный перевод DuckGram", font: .systemFont(ofSize: 15), color: theme.list.itemSecondaryTextColor)
        notice.textAlignment = .center
        self.stack.addArrangedSubview(notice)
        self.stack.setCustomSpacing(28, after: notice)

        for field in [self.amount, self.comment] {
            field.textColor = theme.list.itemPrimaryTextColor
            field.keyboardAppearance = theme.overallDarkAppearance ? .dark : .light
            field.addTarget(self, action: #selector(self.editingBegan), for: .editingDidBegin)
        }
        self.amount.keyboardType = .decimalPad
        self.amount.textAlignment = .center
        self.amount.font = .monospacedDigitSystemFont(ofSize: 36, weight: .bold)
        self.amount.attributedPlaceholder = NSAttributedString(string: "0 GRAM", attributes: [.foregroundColor: theme.list.itemPrimaryTextColor.withAlphaComponent(0.62)])
        self.amount.accessibilityLabel = "Сумма GRAM"
        let icon = UIImageView(image: UIImage(bundleImageName: "Chat/Context Menu/Ton"))
        icon.contentMode = .center
        icon.tintColor = theme.list.itemAccentColor
        icon.frame = CGRect(x: 0, y: 0, width: 32, height: 36)
        self.amount.leftView = icon
        self.amount.leftViewMode = .always
        self.amount.heightAnchor.constraint(equalToConstant: 56).isActive = true
        self.amount.addTarget(self, action: #selector(self.updateBalance), for: .editingChanged)
        self.stack.addArrangedSubview(self.amount)

        self.comment.borderStyle = .roundedRect
        self.comment.isHidden = true
        self.comment.attributedPlaceholder = NSAttributedString(string: "Добавить комментарий", attributes: [.foregroundColor: theme.list.itemPrimaryTextColor.withAlphaComponent(0.62)])
        let commentHeight = self.comment.heightAnchor.constraint(equalToConstant: 44)
        commentHeight.priority = .defaultHigh
        commentHeight.isActive = true
        self.stack.addArrangedSubview(self.comment)

        self.balance.font = .systemFont(ofSize: 15)
        self.balance.textColor = theme.list.itemSecondaryTextColor
        self.balance.textAlignment = .center
        self.stack.addArrangedSubview(self.balance)
        let button = gramButton("Отправить GRAM", theme: theme) { [weak self] in self?.confirm() }
        self.sendButton = button
        self.stack.addArrangedSubview(button)
        self.disposable = (VisualGramLocalAppearance.shared.changes |> deliverOnMainQueue).start(next: { [weak self] _ in self?.updateBalance() })
        self.updateBalance()
    }

    override public func containerLayoutUpdated(_ layout: ContainerViewLayout, transition: ContainedViewLayoutTransition) {
        super.containerLayoutUpdated(layout, transition: transition)
        let top = layout.safeInsets.top
        let bottom = max(layout.intrinsicInsets.bottom, layout.inputHeight ?? 0)
        self.scroll.frame = CGRect(x: 0, y: top, width: layout.size.width, height: max(0, layout.size.height - top - bottom))
        let width = max(1, min(480, layout.size.width - layout.safeInsets.left - layout.safeInsets.right - 32))
        let size = self.stack.systemLayoutSizeFitting(CGSize(width: width, height: 0), withHorizontalFittingPriority: .required, verticalFittingPriority: .fittingSizeLevel)
        self.stack.frame = CGRect(x: (layout.size.width - width) / 2, y: 12, width: width, height: size.height)
        self.scroll.contentSize = CGSize(width: layout.size.width, height: size.height + 24)
        if let field = [self.amount, self.comment].first(where: { $0.isFirstResponder }) {
            self.scroll.scrollRectToVisible(self.scroll.convert(field.bounds, from: field).insetBy(dx: 0, dy: -12), animated: false)
        }
    }

    @objc private func editingBegan() { self.requestAttachmentMenuExpansion() }

    @objc private func updateBalance() {
        let balance = VisualGramLocalAppearance.shared.localGramBalance(accountId: self.context.account.peerId) ?? 0
        self.balance.text = "Баланс: " + gramAmount(balance, data: self.data)
        let amount = VisualGramLocalAppearance.parseGrams(self.amount.text ?? "") ?? 0
        let enabled = !self.sent && !self.confirming && amount > 0 && amount <= balance
        self.sendButton?.isEnabled = enabled
        self.sendButton?.alpha = enabled ? 1 : 0.45
    }

    private func close() {
        self.view.endEditing(true)
        if let dismissAttachment = self.dismissAttachment {
            dismissAttachment()
            if self.sent { self.completed() }
        } else {
            self.dismiss(completion: self.sent ? self.completed : nil)
        }
    }

    private func confirm() {
        guard !self.sent, !self.confirming, let amount = VisualGramLocalAppearance.parseGrams(self.amount.text ?? ""), amount > 0 else { return }
        self.view.endEditing(true)
        let comment = String((self.comment.text ?? "").trimmingCharacters(in: .whitespacesAndNewlines).prefix(256))
        self.confirming = true
        self.updateBalance()
        let alert = textAlertController(context: self.context, title: "Подтвердить перевод", text: "Отправить \(gramAmount(amount, data: self.data)) пользователю \(self.peer.compactDisplayTitle)?", actions: [
            TextAlertAction(type: .genericAction, title: self.data.strings.Common_Cancel, action: { [weak self] in
                self?.confirming = false
                self?.updateBalance()
            }),
            TextAlertAction(type: .defaultAction, title: "Отправить", action: { [weak self] in self?.send(amount: amount, comment: comment.isEmpty ? nil : comment) })
        ], dismissOnOutsideTap: false)
        self.present(alert, in: .window(.root))
    }

    private func send(amount: Int64, comment: String?) {
        guard !self.sent else { return }
        let result = VisualGramLocalAppearance.shared.transferLocalGrams(accountId: self.context.account.peerId, to: self.peer.id, amount: amount, comment: comment, now: Int32(clamping: Int64(Date().timeIntervalSince1970)))
        let error: String
        switch result {
        case .sent:
            self.sent = true
            self.close()
            return
        case .insufficientBalance: error = "Недостаточно GRAM на локальном балансе."
        case .invalidRecipient: error = "Выберите другого получателя."
        case .overflow: error = "Эта сумма превышает доступный лимит получателя."
        case .unavailable: error = "Локальный перевод сейчас недоступен."
        }
        self.confirming = false
        self.updateBalance()
        self.present(textAlertController(context: self.context, title: nil, text: error, actions: [TextAlertAction(type: .defaultAction, title: self.data.strings.Common_OK, action: {})]), in: .window(.root))
    }
}

public final class VisualGramMoneyScreen: ViewController, UITableViewDataSource, UITableViewDelegate {
    private let context: AccountContext
    private let data: PresentationData
    private let table = UITableView(frame: .zero, style: .insetGrouped)
    private let card = ComponentView<Empty>()
    private let cardHost = UIView()
    private lazy var cardHeight = self.cardHost.heightAnchor.constraint(equalToConstant: 1)
    private let header = UIStackView()
    private let peerRequest = MetaDisposable()
    private var selection: Disposable?
    private var changes: Disposable?
    private var entries: [VisualGramGift.StarsTransaction] = []
    private var peers: [EnginePeer.Id: EnginePeer] = [:]
    private var requestedPeerIds: Set<EnginePeer.Id>?
    private var displayedCard: WalletCard?
    private var stickers: [WalletContext.CardSticker] = []
    private var stickerMedia: [String: WalletGiftStickerMedia] = [:]

    public init(context: AccountContext) {
        self.context = context
        self.data = context.sharedContext.currentPresentationData.with { $0 }
        super.init(navigationBarPresentationData: NavigationBarPresentationData(presentationData: self.data))
        self.title = self.data.strings.Settings_Money
    }

    required public init(coder: NSCoder) { preconditionFailure() }
    deinit {
        self.peerRequest.dispose()
        self.selection?.dispose()
        self.changes?.dispose()
    }

    override public func loadDisplayNode() {
        self.displayNode = ASDisplayNode()
        self.displayNodeDidLoad()
        let theme = self.data.theme
        self.view.overrideUserInterfaceStyle = theme.overallDarkAppearance ? .dark : .light
        self.displayNode.backgroundColor = theme.list.blocksBackgroundColor
        self.table.backgroundColor = .clear
        self.table.dataSource = self
        self.table.delegate = self
        self.table.rowHeight = 64
        self.view.addSubview(self.table)

        self.header.axis = .vertical
        self.header.spacing = 12
        self.header.isLayoutMarginsRelativeArrangement = true
        self.header.layoutMargins = UIEdgeInsets(top: 12, left: 16, bottom: 12, right: 16)
        self.header.addArrangedSubview(self.cardHost)
        self.cardHeight.isActive = true
        let actions = UIStackView(arrangedSubviews: [
            gramButton("Пополнить", theme: theme) { [weak self] in
                guard let self else { return }
                presentGramTopUp(on: self, context: self.context, data: self.data)
            },
            gramButton("Отправить", theme: theme) { [weak self] in self?.chooseRecipient() }
        ])
        actions.spacing = 10
        actions.distribution = .fillEqually
        self.header.addArrangedSubview(actions)
        let notice = gramLabel("Локальный баланс DuckGram", font: .systemFont(ofSize: 14), color: theme.list.itemSecondaryTextColor)
        notice.textAlignment = .center
        self.header.addArrangedSubview(notice)
        self.changes = (VisualGramLocalAppearance.shared.changes |> deliverOnMainQueue).start(next: { [weak self] _ in self?.refresh() })
    }

    override public func containerLayoutUpdated(_ layout: ContainerViewLayout, transition: ContainedViewLayoutTransition) {
        super.containerLayoutUpdated(layout, transition: transition)
        let top = self.navigationLayout(layout: layout).navigationFrame.maxY
        self.table.frame = CGRect(x: layout.safeInsets.left, y: top, width: max(0, layout.size.width - layout.safeInsets.left - layout.safeInsets.right), height: max(0, layout.size.height - top))
        self.table.contentInset.bottom = layout.intrinsicInsets.bottom
        self.layoutHeader()
    }

    private func refresh() {
        let id = self.context.account.peerId
        let store = VisualGramLocalAppearance.shared
        let appearance = store.appearance(accountId: id)
        self.entries = (appearance.gramHistory ?? []).reversed().sorted { $0.date > $1.date }
        self.table.reloadData()
        let card = store.displayWalletCard(accountId: id, peerId: id, server: nil, appearanceOverride: appearance)
        if self.displayedCard != card {
            self.displayedCard = card
            self.stickers = (card?.stickers ?? []).compactMap {
                WalletContext.CardSticker(serverSticker: $0, backgroundNftAddress: card?.backgroundNft?.address)
            }
            self.stickerMedia.removeAll()
            for sticker in self.stickers {
                let media = WalletGiftStickerMedia(context: self.context, gift: sticker.gift, modelFile: sticker.modelFile, style: sticker.giftStyle)
                self.stickerMedia[sticker.gift.address] = media
                media.updated = { [weak self] in self?.updateStickers() }
            }
        }
        let ids = Set(self.entries.compactMap { $0.peerId.map { EnginePeer.Id($0) } } + [id])
        if self.requestedPeerIds != ids {
            self.requestedPeerIds = ids
            self.peerRequest.set((self.context.engine.data.get(EngineDataMap(ids.map { TelegramEngine.EngineData.Item.Peer.Peer(id: $0) })) |> deliverOnMainQueue).start(next: { [weak self] peers in
                guard let self, self.requestedPeerIds == ids else { return }
                self.peers = peers.compactMapValues { $0 }
                self.table.reloadData()
                self.layoutHeader()
            }))
        }
        self.layoutHeader()
    }

    private func layoutHeader() {
        let width = self.table.bounds.width
        guard width > 32 else { return }
        let cardWidth = min(width - 32, 430)
        let cardHeight = cardWidth * 220 / 370
        let size = self.card.update(transition: .immediate, component: AnyComponent(WalletCardComponent(
            theme: self.data.theme, balance: self.displayedCard?.balance ?? 0, fiatCurrency: .usd, fiatRate: nil,
            dateTimeFormat: self.data.dateTimeFormat, name: self.peers[self.context.account.peerId]?.compactDisplayTitle.uppercased() ?? "",
            address: "", isVisible: self.view.window != nil, qrPressed: {}
        )), environment: {}, containerSize: CGSize(width: cardWidth, height: cardHeight))
        if let view = self.card.view {
            if view.superview == nil { self.cardHost.addSubview(view) }
            view.frame = CGRect(x: (width - 32 - size.width) / 2, y: 0, width: size.width, height: size.height)
        }
        self.updateStickers()
        self.cardHeight.constant = size.height
        let fitted = self.header.systemLayoutSizeFitting(CGSize(width: width, height: 0), withHorizontalFittingPriority: .required, verticalFittingPriority: .fittingSizeLevel)
        let frame = CGRect(origin: .zero, size: CGSize(width: width, height: fitted.height))
        if self.table.tableHeaderView == nil || self.header.frame != frame {
            self.header.frame = frame
            self.table.tableHeaderView = self.header
        }
    }

    private func updateStickers() {
        guard let card = self.card.view as? WalletCardComponent.View else { return }
        card.setCardStickers(self.stickers, images: self.stickerMedia.compactMapValues { $0.first?.image }, hidden: [])
        let background = self.stickers.last { $0.style != nil }
        card.setGiftStyle(from: background?.style, to: background?.style, origin: .zero, progress: 1,
                          pattern: background.flatMap { self.stickerMedia[$0.gift.address]?.patternImage })
    }

    private func chooseRecipient() {
        let ownId = self.context.account.peerId
        let controller = self.context.sharedContext.makeContactSelectionController(ContactSelectionControllerParams(
            context: self.context, style: .glass, autoDismiss: false, title: { _ in "Выберите получателя" }, isPeerEnabled: { candidate in
                guard case let .peer(.user(user), _, _) = candidate else { return false }
                return user.id != ownId && !user.isDeleted && user.botInfo == nil && !user.flags.contains(.isSupport) && !isServicePeer(user)
            }
        ))
        controller.navigationPresentation = .modal
        self.selection?.dispose()
        self.selection = (controller.result |> deliverOnMainQueue).start(next: { [weak self, weak controller] result in
            guard let self, let controller, let result, let first = result.0.first, case let .peer(peer, _, _) = first else { return }
            self.selection?.dispose()
            controller.dismiss(completion: { [weak self] in
                guard let self else { return }
                self.push(VisualGramSendMoneyScreen(context: self.context, peer: peer))
            })
        })
        self.push(controller)
    }

    public func tableView(_ tableView: UITableView, didSelectRowAt indexPath: IndexPath) {
        tableView.deselectRow(at: indexPath, animated: true)
        let entry = self.entries[indexPath.row]
        guard entry.kind == .transfer else { return }
        let title = entry.amount > 0 ? "Входящий локальный перевод" : "Исходящий локальный перевод"
        let amount = gramAmount(abs(max(-Int64.max, entry.amount)), data: self.data)
        let peer = entry.peerId.flatMap { self.peers[EnginePeer.Id($0)]?.compactDisplayTitle }
        let text = [amount, peer, entry.comment].compactMap { $0 }.joined(separator: "\n\n")
        self.present(textAlertController(context: self.context, title: title, text: text, actions: [TextAlertAction(type: .defaultAction, title: self.data.strings.Common_OK, action: {})]), in: .window(.root))
    }

    public func tableView(_ tableView: UITableView, numberOfRowsInSection section: Int) -> Int { self.entries.count }

    public func tableView(_ tableView: UITableView, cellForRowAt indexPath: IndexPath) -> UITableViewCell {
        let entry = self.entries[indexPath.row]
        let theme = self.data.theme
        let cell = tableView.dequeueReusableCell(withIdentifier: "transfer") ?? UITableViewCell(style: .subtitle, reuseIdentifier: "transfer")
        let title = entry.title ?? (entry.amount > 0 ? "Зачисление" : "Списание")
        cell.backgroundColor = theme.list.itemBlocksBackgroundColor
        cell.selectionStyle = entry.kind == .transfer ? .default : .none
        cell.textLabel?.textColor = theme.list.itemPrimaryTextColor
        cell.textLabel?.text = entry.peerId.flatMap { self.peers[EnginePeer.Id($0)]?.compactDisplayTitle } ?? title
        cell.detailTextLabel?.numberOfLines = 2
        cell.detailTextLabel?.textColor = theme.list.itemSecondaryTextColor
        let date = Date(timeIntervalSince1970: TimeInterval(entry.date)).formatted(date: .abbreviated, time: .shortened)
        cell.detailTextLabel?.text = entry.peerId == nil ? date : title + " · " + date
        let amount = gramLabel((entry.amount < 0 ? "−" : "+") + gramAmount(abs(max(-Int64.max, entry.amount)), data: self.data),
                               font: .monospacedDigitSystemFont(ofSize: 14, weight: .semibold), color: entry.amount > 0 ? theme.list.itemAccentColor : theme.list.itemPrimaryTextColor)
        amount.sizeToFit()
        cell.accessoryView = amount
        return cell
    }
}
