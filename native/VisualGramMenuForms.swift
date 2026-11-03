import UIKit
import AsyncDisplayKit
import Display
import SwiftSignalKit
import AccountContext
import TelegramCore
import TelegramPresentationData

final class VisualGramDetailsController: ViewController, UIPickerViewDataSource, UIPickerViewDelegate {
    private let context: AccountContext
    private let fields: [(String, String)]
    private let initialDate: Int32
    private let seconds: Bool
    private let tonIndex: Int?
    private let phoneMode: Bool
    private let saveValues: ([String], Int32) -> Bool
    private let scroll = UIScrollView()
    private let stack = UIStackView()
    private var inputs: [UITextField] = []
    private let datePicker = UIDatePicker()
    private let secondPicker = UIPickerView()
    private let price = UILabel()

    init(context: AccountContext, title: String, fields: [(String, String)], date: Int32, seconds: Bool = false, tonIndex: Int? = nil, phoneMode: Bool = false, save: @escaping ([String], Int32) -> Bool) {
        self.context = context; self.fields = fields; self.initialDate = date; self.seconds = seconds; self.tonIndex = tonIndex; self.phoneMode = phoneMode; self.saveValues = save
        super.init(navigationBarPresentationData: NavigationBarPresentationData(presentationData: context.sharedContext.currentPresentationData.with { $0 }))
        self.title = title
        self.navigationItem.rightBarButtonItem = UIBarButtonItem(title: "Сохранить", style: .done, target: self, action: #selector(self.save))
    }
    required init(coder: NSCoder) { preconditionFailure() }
    override func loadDisplayNode() {
        self.displayNode = ASDisplayNode(); self.displayNodeDidLoad()
        let theme = self.context.sharedContext.currentPresentationData.with { $0 }.theme
        self.displayNode.backgroundColor = theme.list.blocksBackgroundColor
        self.scroll.keyboardDismissMode = .interactive; self.view.addSubview(self.scroll)
        self.stack.axis = .vertical; self.stack.spacing = 12; self.scroll.addSubview(self.stack)
        for (index, field) in self.fields.enumerated() {
            let input = UITextField(); input.placeholder = field.0; input.text = field.1
            input.borderStyle = .roundedRect; input.autocorrectionType = .no; input.autocapitalizationType = .none
            input.textColor = theme.list.itemPrimaryTextColor; input.backgroundColor = theme.list.itemBlocksBackgroundColor
            input.font = .systemFont(ofSize: 17); let inputHeight = input.heightAnchor.constraint(equalToConstant: 48); inputHeight.priority = .defaultHigh; inputHeight.isActive = true
            if index == self.tonIndex { input.keyboardType = .decimalPad }
            input.addTarget(self, action: #selector(self.changed), for: .editingChanged)
            self.inputs.append(input); self.stack.addArrangedSubview(input)
        }
        self.price.font = .systemFont(ofSize: 15); self.price.textColor = theme.list.itemSecondaryTextColor; self.price.numberOfLines = 0
        self.stack.addArrangedSubview(self.price)
        self.datePicker.preferredDatePickerStyle = .wheels
        self.datePicker.datePickerMode = self.seconds ? .dateAndTime : .date
        self.datePicker.date = Date(timeIntervalSince1970: TimeInterval(self.initialDate))
        let dateHeight = self.datePicker.heightAnchor.constraint(equalToConstant: 216); dateHeight.priority = .defaultHigh; dateHeight.isActive = true
        self.stack.addArrangedSubview(self.datePicker)
        if self.seconds {
            let label = UILabel(); label.text = "Секунды"; label.textColor = theme.list.itemSecondaryTextColor
            self.stack.addArrangedSubview(label)
            self.secondPicker.dataSource = self; self.secondPicker.delegate = self
            self.secondPicker.heightAnchor.constraint(equalToConstant: 110).isActive = true
            self.stack.addArrangedSubview(self.secondPicker)
            self.secondPicker.selectRow(Calendar.current.component(.second, from: self.datePicker.date), inComponent: 0, animated: false)
        }
        self.changed()
    }
    override func containerLayoutUpdated(_ layout: ContainerViewLayout, transition: ContainedViewLayoutTransition) {
        super.containerLayoutUpdated(layout, transition: transition)
        let top = self.navigationLayout(layout: layout).navigationFrame.maxY
        self.scroll.frame = CGRect(x: 0, y: top, width: layout.size.width, height: max(0, layout.size.height - top))
        self.scroll.contentInset.bottom = max(layout.inputHeight ?? 0, layout.intrinsicInsets.bottom)
        let width = max(0, layout.size.width - layout.safeInsets.left - layout.safeInsets.right - 32)
        let size = self.stack.systemLayoutSizeFitting(CGSize(width: width, height: 0), withHorizontalFittingPriority: .required, verticalFittingPriority: .fittingSizeLevel)
        self.stack.frame = CGRect(x: layout.safeInsets.left + 16, y: 16, width: width, height: size.height)
        self.scroll.contentSize = CGSize(width: layout.size.width, height: size.height + 32)
    }
    @objc private func changed() {
        let collectible = !self.phoneMode || (self.inputs.first?.text ?? "").filter { $0.isNumber }.hasPrefix("888")
        self.datePicker.isHidden = !collectible
        if let index = self.tonIndex, self.inputs.indices.contains(index) {
            self.inputs[index].isHidden = !collectible; self.price.isHidden = !collectible
            let rate = self.context.currentAppConfiguration.with { $0 }.data?["ton_usd_rate"] as? Double
            if let rate, rate.isFinite, rate > 0, let nano = VisualGramLocalAppearance.parseGrams(self.inputs[index].text ?? "") {
                let usd = Double(nano) / 1_000_000_000 * rate
                self.price.text = String(format: "≈ %.2f USDT", usd)
            } else { self.price.text = "Стоимость появится после загрузки курса TON." }
        } else { self.price.isHidden = true }
        self.requestLayout(transition: .immediate)
    }
    func numberOfComponents(in pickerView: UIPickerView) -> Int { 1 }
    func pickerView(_ pickerView: UIPickerView, numberOfRowsInComponent component: Int) -> Int { 60 }
    func pickerView(_ pickerView: UIPickerView, titleForRow row: Int, forComponent component: Int) -> String? { String(format: "%02d", row) }
    @objc private func save() {
        self.view.endEditing(true)
        let date: Date
        if self.seconds {
            var components = Calendar.current.dateComponents([.year, .month, .day, .hour, .minute], from: self.datePicker.date)
            components.second = self.secondPicker.selectedRow(inComponent: 0)
            guard let value = Calendar.current.date(from: components) else { return }; date = value
        } else { date = self.datePicker.date }
        guard date.timeIntervalSince1970 >= 0, date.timeIntervalSince1970 <= Double(Int32.max) else { return }
        if self.saveValues(self.inputs.map { $0.text ?? "" }, Int32(date.timeIntervalSince1970)) { self.dismiss() }
    }
}

struct VisualGramListRow {
    let id: String
    let title: String
    let subtitle: String
    let gift: VisualGramGift?
}

private final class VisualGramListCell: UITableViewCell {
    let giftPreview = VisualGramGiftCell(frame: .zero)
    override init(style: UITableViewCell.CellStyle, reuseIdentifier: String?) {
        super.init(style: .subtitle, reuseIdentifier: reuseIdentifier)
        self.contentView.addSubview(self.giftPreview); self.giftPreview.isUserInteractionEnabled = false
        self.giftPreview.clipsToBounds = true; self.giftPreview.contentView.clipsToBounds = true
    }
    required init?(coder: NSCoder) { preconditionFailure() }
    override func layoutSubviews() {
        super.layoutSubviews()
        self.giftPreview.frame = CGRect(x: 12, y: 5, width: 48, height: 64)
        let x: CGFloat = self.giftPreview.isHidden ? 16 : 72
        self.textLabel?.frame.origin.x = x; self.detailTextLabel?.frame.origin.x = x
        self.textLabel?.frame.size.width = max(0, self.contentView.bounds.width - x - 12)
        self.detailTextLabel?.frame.size.width = max(0, self.contentView.bounds.width - x - 12)
    }
}

final class VisualGramListController: ViewController, UITableViewDataSource, UITableViewDelegate, UITableViewDragDelegate, UITableViewDropDelegate {
    private let context: AccountContext
    private let target: EnginePeer.Id
    private let rows: () -> [VisualGramListRow]
    private let reorder: (([String]) -> Bool)?
    private let openRow: (String) -> Void
    private let editRow: (String) -> Void
    private let deleteRow: (String) -> Void
    private let allowsEditing: Bool
    private let deleteTitle: String
    private let deleteConfirmation: String?
    private let table = UITableView(frame: .zero, style: .insetGrouped)
    private var items: [VisualGramListRow] = []
    private var moving = false
    private var disposable: Disposable?
    init(context: AccountContext, target: EnginePeer.Id, title: String, rows: @escaping () -> [VisualGramListRow], reorder: (([String]) -> Bool)?, open: @escaping (String) -> Void, edit: @escaping (String) -> Void, delete: @escaping (String) -> Void, allowsEditing: Bool = true, deleteTitle: String = "Удалить", deleteConfirmation: String? = nil) {
        self.context = context; self.target = target; self.rows = rows; self.reorder = reorder; self.openRow = open; self.editRow = edit; self.deleteRow = delete
        self.allowsEditing = allowsEditing; self.deleteTitle = deleteTitle; self.deleteConfirmation = deleteConfirmation
        super.init(navigationBarPresentationData: NavigationBarPresentationData(presentationData: context.sharedContext.currentPresentationData.with { $0 }))
        self.title = title
    }
    required init(coder: NSCoder) { preconditionFailure() }
    deinit { self.disposable?.dispose() }
    override func loadDisplayNode() {
        self.displayNode = ASDisplayNode(); self.displayNodeDidLoad()
        self.displayNode.backgroundColor = self.context.sharedContext.currentPresentationData.with { $0 }.theme.list.blocksBackgroundColor
        self.view.disablesInteractiveTransitionGestureRecognizerNow = { true }
        self.table.disablesInteractiveTransitionGestureRecognizerNow = { true }
        self.table.backgroundColor = .clear; self.table.dataSource = self; self.table.delegate = self
        self.table.dragDelegate = self; self.table.dropDelegate = self; self.table.dragInteractionEnabled = self.reorder != nil
        self.table.rowHeight = 74; self.table.register(VisualGramListCell.self, forCellReuseIdentifier: "item")
        self.view.addSubview(self.table)
        self.disposable = (VisualGramLocalAppearance.shared.changes |> deliverOnMainQueue).start(next: { [weak self] _ in self?.refresh() })
        self.refresh()
    }
    private func refresh() { guard !self.moving else { return }; self.items = self.rows(); self.table.reloadData() }
    override func containerLayoutUpdated(_ layout: ContainerViewLayout, transition: ContainedViewLayoutTransition) {
        super.containerLayoutUpdated(layout, transition: transition)
        let top = self.navigationLayout(layout: layout).navigationFrame.maxY
        self.table.frame = CGRect(x: layout.safeInsets.left, y: top, width: max(0, layout.size.width - layout.safeInsets.left - layout.safeInsets.right), height: max(0, layout.size.height - top))
        self.table.contentInset.bottom = max(layout.intrinsicInsets.bottom, layout.safeInsets.bottom)
    }
    func tableView(_ tableView: UITableView, numberOfRowsInSection section: Int) -> Int { self.items.count }
    func tableView(_ tableView: UITableView, cellForRowAt indexPath: IndexPath) -> UITableViewCell {
        let cell = tableView.dequeueReusableCell(withIdentifier: "item", for: indexPath) as! VisualGramListCell
        let row = self.items[indexPath.row], theme = self.context.sharedContext.currentPresentationData.with { $0 }.theme
        cell.textLabel?.text = row.title; cell.detailTextLabel?.text = row.subtitle; cell.detailTextLabel?.numberOfLines = 2
        cell.textLabel?.textColor = theme.list.itemPrimaryTextColor; cell.detailTextLabel?.textColor = theme.list.itemSecondaryTextColor
        cell.backgroundColor = theme.list.itemBlocksBackgroundColor
        cell.giftPreview.isHidden = row.gift == nil
        if let gift = row.gift { cell.giftPreview.update(context: self.context, gift: gift, target: self.target, selected: false) }
        if self.reorder != nil {
            let handle = UIImageView(image: UIImage(systemName: "line.3.horizontal")); handle.tintColor = theme.list.itemSecondaryTextColor
            handle.contentMode = .center; handle.frame = CGRect(x: 0, y: 0, width: 36, height: 36)
            handle.accessibilityLabel = "Изменить порядок"; cell.accessoryView = handle
        } else { cell.accessoryView = nil }
        return cell
    }
    func tableView(_ tableView: UITableView, didSelectRowAt indexPath: IndexPath) { tableView.deselectRow(at: indexPath, animated: true); self.openRow(self.items[indexPath.row].id) }
    func tableView(_ tableView: UITableView, leadingSwipeActionsConfigurationForRowAt indexPath: IndexPath) -> UISwipeActionsConfiguration? {
        guard self.allowsEditing else { return nil }
        let id = self.items[indexPath.row].id
        return UISwipeActionsConfiguration(actions: [UIContextualAction(style: .normal, title: "Изменить", handler: { [weak self] _, _, done in done(true); self?.editRow(id) })])
    }
    func tableView(_ tableView: UITableView, trailingSwipeActionsConfigurationForRowAt indexPath: IndexPath) -> UISwipeActionsConfiguration? {
        guard self.allowsEditing else { return nil }
        let id = self.items[indexPath.row].id
        return UISwipeActionsConfiguration(actions: [UIContextualAction(style: .destructive, title: self.deleteTitle, handler: { [weak self] _, _, done in
            guard let self else { done(false); return }
            let alert = UIAlertController(title: self.deleteTitle + "?", message: self.deleteConfirmation, preferredStyle: .alert)
            alert.addAction(UIAlertAction(title: "Отмена", style: .cancel, handler: { _ in done(false) }))
            alert.addAction(UIAlertAction(title: self.deleteTitle, style: .destructive, handler: { _ in self.deleteRow(id); done(true) }))
            self.present(alert, animated: true)
        })])
    }
    func tableView(_ tableView: UITableView, itemsForBeginning session: UIDragSession, at indexPath: IndexPath) -> [UIDragItem] {
        guard self.reorder != nil, !self.moving, let cell = tableView.cellForRow(at: indexPath), session.location(in: cell).x >= cell.bounds.width - 64 else { return [] }
        let id = self.items[indexPath.row].id, item = UIDragItem(itemProvider: NSItemProvider(object: self.items[indexPath.row].id as NSString))
        item.localObject = id; return [item]
    }
    func tableView(_ tableView: UITableView, dropSessionDidUpdate session: UIDropSession, withDestinationIndexPath destinationIndexPath: IndexPath?) -> UITableViewDropProposal {
        guard self.reorder != nil, session.localDragSession != nil, !self.moving,
              let id = session.items.first?.localObject as? String,
              let source = self.items.firstIndex(where: { $0.id == id }), !self.items.isEmpty else { return UITableViewDropProposal(operation: .forbidden) }
        let destination = min(destinationIndexPath?.row ?? self.items.count - 1, self.items.count - 1)
        guard (self.items[source].gift?.pinnedToTop == true) == (self.items[destination].gift?.pinnedToTop == true) else { return UITableViewDropProposal(operation: .forbidden) }
        return UITableViewDropProposal(operation: .move, intent: .insertAtDestinationIndexPath)
    }
    func tableView(_ tableView: UITableView, performDropWith coordinator: UITableViewDropCoordinator) {
        guard let reorder = self.reorder, !self.moving, let item = coordinator.items.first, let id = item.dragItem.localObject as? String, let source = self.items.firstIndex(where: { $0.id == id }) else { return }
        let destination = min(coordinator.destinationIndexPath?.row ?? self.items.count - 1, self.items.count - 1)
        guard source != destination else { return }
        self.moving = true
        var tableFinished = false, dropFinished = false, committed = false
        let finish: () -> Void = { [weak self] in
            guard tableFinished, dropFinished, !committed, let self else { return }
            committed = true
            let success = reorder(self.items.map { $0.id }); self.moving = false; self.refresh()
            if !success {
                let alert = UIAlertController(title: "Список изменился", message: "Повтори перемещение для актуального списка.", preferredStyle: .alert)
                alert.addAction(UIAlertAction(title: "OK", style: .default)); self.present(alert, animated: true)
            }
        }
        self.table.performBatchUpdates({
            let moved = self.items.remove(at: source); self.items.insert(moved, at: destination)
            self.table.moveRow(at: IndexPath(row: source, section: 0), to: IndexPath(row: destination, section: 0))
        }, completion: { _ in tableFinished = true; finish() })
        let animation = coordinator.drop(item.dragItem, toRowAt: IndexPath(row: destination, section: 0))
        animation.addCompletion { _ in dropFinished = true; finish() }
    }
}
