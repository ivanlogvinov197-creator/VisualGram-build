import Foundation
import UIKit
import Display
import SwiftSignalKit
import TelegramCore
import TelegramPresentationData
import PresentationDataUtils
import ItemListUI
import AccountContext
import PeerNameColorItem

private struct VisualGramChannelSettingsDraft: Equatable {
    let original: VisualGramChannelProperties
    var edited: VisualGramChannelProperties
    var subscriberText: String

    init(properties: VisualGramChannelProperties) {
        self.original = properties
        self.edited = properties
        self.subscriberText = properties.subscriberCount.map(String.init) ?? ""
    }

    var hasChanges: Bool {
        return self.edited != self.original ||
            self.subscriberText != (self.original.subscriberCount.map(String.init) ?? "")
    }

    func apply(to properties: inout VisualGramChannelProperties, subscriberCount: Int32?) {
        if self.edited.title != self.original.title { properties.title = self.edited.title }
        if self.edited.about != self.original.about { properties.about = self.edited.about }
        if self.edited.username != self.original.username { properties.username = self.edited.username }
        if self.edited.verified != self.original.verified { properties.verified = self.edited.verified }
        if self.edited.signaturesEnabled != self.original.signaturesEnabled { properties.signaturesEnabled = self.edited.signaturesEnabled }
        if self.edited.showAuthors != self.original.showAuthors { properties.showAuthors = self.edited.showAuthors }
        if self.edited.color != self.original.color { properties.color = self.edited.color }
        if self.subscriberText != (self.original.subscriberCount.map(String.init) ?? "") {
            properties.subscriberCount = subscriberCount
        }
    }
}

private final class VisualGramChannelSettingsActions {
    let context: AccountContext
    let sourcePeerId: EnginePeer.Id
    let changes: ValuePromise<VisualGramChannelSettingsDraft?>
    weak var controller: ItemListController?
    private var draft: VisualGramChannelSettingsDraft?

    init(context: AccountContext, sourcePeerId: EnginePeer.Id) {
        self.context = context
        self.sourcePeerId = sourcePeerId
        let record = VisualGramLocalAppearance.shared.visualChannel(accountId: context.account.peerId, sourcePeerId: sourcePeerId)
        let draft = record.flatMap { $0.isCopied ? VisualGramChannelSettingsDraft(properties: $0.properties) : nil }
        self.draft = draft
        self.changes = ValuePromise(draft, ignoreRepeated: true)
    }

    func update(_ edit: (inout VisualGramChannelSettingsDraft) -> Void) {
        guard var draft = self.draft else { return }
        edit(&draft)
        self.draft = draft
        self.changes.set(draft)
    }

    func save() {
        guard let draft = self.draft, draft.hasChanges else { return }
        guard !draft.edited.title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            self.showError("Введите название канала.")
            return
        }
        if let username = draft.edited.username, !username.isEmpty {
            let name = username.hasPrefix("@") ? String(username.dropFirst()) : username
            let allowed = CharacterSet(charactersIn: "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_")
            guard !name.isEmpty, name.count <= 32, name.unicodeScalars.allSatisfy({ allowed.contains($0) }) else {
                self.showError("Юзернейм может содержать до 32 латинских букв, цифр и знаков подчёркивания.")
                return
            }
        }

        let subscriberCount: Int32?
        if draft.subscriberText.isEmpty {
            subscriberCount = nil
        } else if let count = Int32(draft.subscriberText), count >= 0 {
            subscriberCount = count
        } else {
            self.showError("Введите число подписчиков от 0 до 2 147 483 647.")
            return
        }

        let saved = VisualGramLocalAppearance.shared.updateVisualChannelProperties(accountId: self.context.account.peerId, sourcePeerId: self.sourcePeerId) { properties in
            draft.apply(to: &properties, subscriberCount: subscriberCount)
        }
        guard saved else {
            self.showError("Не удалось сохранить настройки канала.")
            return
        }
        self.controller?.dismiss()
    }

    func remove() {
        self.controller?.present(textAlertController(
            context: self.context,
            title: "Удалить копию канала?",
            text: "Настройки копии и её посты будут удалены с устройства.",
            actions: [
                TextAlertAction(type: .genericAction, title: "Отмена", action: {}),
                TextAlertAction(type: .defaultDestructiveAction, title: "Удалить", action: { [weak self] in
                    guard let self else { return }
                    if VisualGramLocalAppearance.shared.removeVisualChannelCopy(accountId: self.context.account.peerId, sourcePeerId: self.sourcePeerId) {
                        self.controller?.dismiss()
                    } else {
                        self.showError("Не удалось удалить копию канала.")
                    }
                })
            ]
        ), in: .window(.root))
    }

    private func showError(_ message: String) {
        self.controller?.present(textAlertController(context: self.context, title: nil, text: message, actions: [
            TextAlertAction(type: .defaultAction, title: "ОК", action: {})
        ]), in: .window(.root))
    }
}

private struct VisualGramChannelSettingsEntry: ItemListNodeEntry {
    enum Row: Equatable {
        case title(String)
        case about(String)
        case username(String)
        case subscriberCount(String)
        case verified(Bool)
        case signatures(Bool)
        case authors(Bool, enabled: Bool)
        case color(Int32?)
        case header(String)
        case help(String)
        case remove
    }

    let stableId: Int32
    let section: ItemListSectionId
    let row: Row
    let theme: PresentationTheme

    static func ==(lhs: Self, rhs: Self) -> Bool {
        return lhs.stableId == rhs.stableId && lhs.section == rhs.section && lhs.row == rhs.row && lhs.theme === rhs.theme
    }

    static func <(lhs: Self, rhs: Self) -> Bool {
        return lhs.stableId < rhs.stableId
    }

    func item(presentationData: ItemListPresentationData, arguments: Any) -> ListViewItem {
        let actions = arguments as! VisualGramChannelSettingsActions

        func input(_ title: String, _ value: String, placeholder: String, type: ItemListSingleLineInputItemType, textUpdated: @escaping (String) -> Void) -> ListViewItem {
            return ItemListSingleLineInputItem(
                presentationData: presentationData,
                title: NSAttributedString(string: title, font: Font.regular(presentationData.fontSize.itemListBaseFontSize), textColor: presentationData.theme.list.itemPrimaryTextColor),
                text: value,
                placeholder: placeholder,
                type: type,
                clearType: .onFocus,
                sectionId: self.section,
                textUpdated: textUpdated,
                action: {}
            )
        }

        func toggle(_ title: String, _ value: Bool, enabled: Bool = true, updated: @escaping (Bool) -> Void) -> ListViewItem {
            return ItemListSwitchItem(presentationData: presentationData, title: title, value: value, enabled: enabled, sectionId: self.section, style: .blocks, updated: updated)
        }

        switch self.row {
        case let .title(value):
            return input("Название", value, placeholder: "Название канала", type: .regular(capitalization: true, autocorrection: true)) { value in
                actions.update { $0.edited.title = value }
            }
        case let .about(value):
            return ItemListMultilineInputItem(presentationData: presentationData, text: value, placeholder: "Описание канала", maxLength: nil, sectionId: self.section, style: .blocks, minimalHeight: 70, textUpdated: { value in
                actions.update { $0.edited.about = value }
            })
        case let .username(value):
            return input("Юзернейм", value, placeholder: "@username", type: .regular(capitalization: false, autocorrection: false)) { value in
                actions.update { $0.edited.username = value.isEmpty ? nil : value }
            }
        case let .subscriberCount(value):
            return input("Подписчики", value, placeholder: "Количество", type: .number) { value in
                actions.update { $0.subscriberText = value }
            }
        case let .verified(value):
            return toggle("Галочка", value) { value in
                actions.update { $0.edited.verified = value }
            }
        case let .signatures(value):
            return toggle("Подписывать посты", value) { value in
                actions.update { draft in
                    draft.edited.signaturesEnabled = value
                    if !value { draft.edited.showAuthors = false }
                }
            }
        case let .authors(value, enabled):
            return toggle("Показывать профили авторов", value, enabled: enabled) { value in
                actions.update { $0.edited.showAuthors = value }
            }
        case let .color(value):
            return PeerNameColorItem(theme: presentationData.theme, colors: actions.context.peerNameColors, mode: .name, displayEmptyColor: true, currentColor: value.map(PeerNameColor.init(rawValue:)), updated: { color in
                actions.update { $0.edited.color = color?.rawValue }
            }, sectionId: self.section, strings: presentationData.strings)
        case let .header(title):
            return ItemListSectionHeaderItem(presentationData: presentationData, text: title, sectionId: self.section)
        case let .help(text):
            return ItemListTextItem(presentationData: presentationData, text: .plain(text), sectionId: self.section)
        case .remove:
            return ItemListActionItem(presentationData: presentationData, title: "Удалить копию", kind: .destructive, alignment: .natural, sectionId: self.section, style: .blocks, action: actions.remove)
        }
    }
}

func visualGramChannelSettingsController(context: AccountContext, sourcePeerId: EnginePeer.Id) -> ViewController {
    let actions = VisualGramChannelSettingsActions(context: context, sourcePeerId: sourcePeerId)
    let signal = combineLatest(context.sharedContext.presentationData, actions.changes.get(), VisualGramLocalAppearance.shared.changes)
    |> deliverOnMainQueue
    |> map { presentationData, draft, _ -> (ItemListControllerState, (ItemListNodeState, Any)) in
        let listPresentationData = ItemListPresentationData(presentationData)
        let canEdit = VisualGramLocalAppearance.shared.visualChannel(accountId: context.account.peerId, sourcePeerId: sourcePeerId)?.isCopied == true
        var entries: [VisualGramChannelSettingsEntry] = []
        var save: ItemListNavigationButton?

        func append(_ id: Int32, _ section: ItemListSectionId, _ row: VisualGramChannelSettingsEntry.Row) {
            entries.append(VisualGramChannelSettingsEntry(stableId: id, section: section, row: row, theme: presentationData.theme))
        }

        if canEdit, let draft {
            append(0, 0, .help("Правки видны в этом приложении."))
            append(1, 1, .title(draft.edited.title))
            append(2, 1, .username(draft.edited.username ?? ""))
            append(3, 2, .header("Описание"))
            append(4, 2, .about(draft.edited.about))
            append(5, 3, .subscriberCount(draft.subscriberText))
            append(6, 3, .help("Чтобы убрать подмену количества подписчиков, оставьте поле пустым."))
            append(7, 4, .header("Оформление"))
            append(8, 4, .verified(draft.edited.verified))
            append(9, 4, .color(draft.edited.color))
            append(10, 5, .header("Публикации"))
            append(11, 5, .signatures(draft.edited.signaturesEnabled))
            append(12, 5, .authors(draft.edited.showAuthors, enabled: draft.edited.signaturesEnabled))
            append(13, 6, .remove)
            save = ItemListNavigationButton(content: .text("Сохранить"), style: .bold, enabled: draft.hasChanges, action: actions.save)
        } else {
            append(0, 0, .help("Визуальный канал недоступен."))
        }

        let controllerState = ItemListControllerState(presentationData: listPresentationData, title: .text("Настройки канала"), leftNavigationButton: nil, rightNavigationButton: save, backNavigationButton: nil)
        let listState = ItemListNodeState(presentationData: listPresentationData, entries: entries, style: .blocks, animateChanges: false)
        return (controllerState, (listState, actions))
    }
    let controller = ItemListController(context: context, state: signal)
    actions.controller = controller
    return controller
}
