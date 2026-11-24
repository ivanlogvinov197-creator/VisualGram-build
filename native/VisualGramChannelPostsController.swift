import Foundation
import UIKit
import AccountContext
import AsyncDisplayKit
import ContextUI
import Display
import ItemListUI
import PresentationDataUtils
import SwiftSignalKit
import TelegramCore
import TelegramPresentationData

private let visualGramChannelPostLimit = 4096

private enum VisualGramChannelPostRowTag: ItemListItemTag, Equatable {
    case input
    case source

    func isEqual(to other: ItemListItemTag) -> Bool {
        return (other as? Self) == self
    }
}

private struct VisualGramChannelPostsEntry: ItemListNodeEntry {
    enum Identifier: Hashable {
        case overview
        case description
        case compose
        case source
        case posts
        case empty
        case post(UUID)
        case draft
        case draftHelp
    }

    enum Content: Equatable {
        case overview(title: String, subtitle: String, verified: Bool, color: Int32?, source: EnginePeer?)
        case note(String)
        case header(String)
        case compose
        case source
        case post(VisualGramChannelPost, details: String)
        case draft(String)
    }

    let stableId: Identifier
    let section: ItemListSectionId
    let index: Int
    let content: Content

    var tag: ItemListItemTag? {
        switch self.stableId {
        case .draft: return VisualGramChannelPostRowTag.input
        case .source: return VisualGramChannelPostRowTag.source
        default: return nil
        }
    }

    static func < (lhs: Self, rhs: Self) -> Bool {
        return lhs.section == rhs.section ? lhs.index < rhs.index : lhs.section < rhs.section
    }

    func item(presentationData: ItemListPresentationData, arguments: Any) -> ListViewItem {
        let actions = arguments as! VisualGramChannelPostsActions
        switch self.content {
        case let .overview(title, subtitle, verified, color, source):
            let theme = presentationData.theme
            let titleColor = color.map {
                actions.context.peerNameColors.get(PeerNameColor(rawValue: $0), dark: theme.overallDarkAppearance).main
            } ?? theme.list.itemPrimaryTextColor
            let displayTitle = verified ? title + "  ✓" : title
            let attributed = NSAttributedString(
                string: displayTitle,
                attributes: [.font: Font.semibold(20.0), .foregroundColor: titleColor]
            )
            return ItemListDisclosureItem(
                presentationData: presentationData, systemStyle: .glass,
                context: actions.context, iconPeer: source, title: displayTitle, attributedTitle: attributed,
                label: subtitle, labelStyle: .multilineDetailText, sectionId: self.section,
                style: .blocks, disclosureStyle: .none, action: nil
            )
        case let .note(message):
            return ItemListTextItem(presentationData: presentationData, text: .plain(message), sectionId: self.section)
        case let .header(title):
            return ItemListSectionHeaderItem(presentationData: presentationData, text: title, sectionId: self.section)
        case .compose:
            return ItemListActionItem(presentationData: presentationData, title: "Написать пост", kind: .generic,
                                      alignment: .natural, sectionId: self.section, style: .blocks, action: {
                actions.openEditor(post: nil)
            })
        case .source:
            return ItemListDisclosureItem(presentationData: presentationData, title: "Предпросмотр оригинала",
                                          label: "", sectionId: self.section, style: .blocks, action: {
                actions.openSource()
            }, tag: VisualGramChannelPostRowTag.source)
        case let .post(post, details):
            return ItemListTextWithLabelItem(presentationData: presentationData, label: details, text: post.text,
                                             style: .blocks, enabledEntityTypes: [], multiline: true,
                                             sectionId: self.section, action: {
                actions.openPostActions(post)
            }, longTapAction: {
                actions.openPostActions(post)
            })
        case let .draft(text):
            return ItemListMultilineInputItem(
                presentationData: presentationData, systemStyle: .glass, text: text, placeholder: "Текст поста",
                maxLength: nil, sectionId: self.section, style: .blocks, minimalHeight: 150.0,
                textUpdated: { actions.draft.set($0) },
                shouldUpdateText: { $0.utf16.count <= visualGramChannelPostLimit }, tag: VisualGramChannelPostRowTag.input
            )
        }
    }
}

private final class VisualGramChannelPostsActions {
    let context: AccountContext
    let sourcePeerId: EnginePeer.Id
    let draft: ValuePromise<String>
    weak var controller: ItemListController?

    init(context: AccountContext, sourcePeerId: EnginePeer.Id, text: String = "") {
        self.context = context
        self.sourcePeerId = sourcePeerId
        self.draft = ValuePromise(text, ignoreRepeated: true)
    }

    var copy: VisualGramChannelRecord? {
        let record = VisualGramLocalAppearance.shared.visualChannel(
            accountId: self.context.account.peerId, sourcePeerId: self.sourcePeerId
        )
        return record?.isCopied == true ? record : nil
    }

    func openSettings() {
        guard self.copy != nil else { return }
        self.controller?.push(visualGramChannelSettingsController(context: self.context, sourcePeerId: self.sourcePeerId))
    }

    func openSource() {
        guard let controller = self.controller, self.copy != nil else { return }
        let preview = self.context.sharedContext.makeChatController(
            context: self.context, chatLocation: .peer(id: self.sourcePeerId), subject: nil,
            botStart: nil, mode: .standard(.previewing), params: nil
        )
        preview.canReadHistory.set(false)
        let presentation = self.context.sharedContext.currentPresentationData.with { $0 }
        let items: [ContextMenuItem] = [
            .action(ContextMenuActionItem(text: "Закрыть", icon: { _ in nil }, action: { _, dismiss in
                dismiss(.default)
            }))
        ]
        let sourceNode: ASDisplayNode = controller.itemNode(forTag: VisualGramChannelPostRowTag.source) ?? controller.displayNode
        let overlay = makeContextController(
            presentationData: presentation,
            source: .controller(ContextControllerContentSourceImpl(
                controller: preview, sourceNode: sourceNode, passthroughTouches: false
            )),
            items: .single(ContextController.Items(content: .list(items)))
        )
        controller.presentInGlobalOverlay(overlay)
    }

    func openPostActions(_ post: VisualGramChannelPost) {
        guard self.copy?.posts.contains(where: { $0.id == post.id }) == true else { return }
        self.controller?.present(textAlertController(
            context: self.context, title: "Действия с постом", text: "",
            actions: [
                TextAlertAction(type: .defaultAction, title: "Редактировать", action: { [weak self] in
                    self?.openEditor(post: post)
                }),
                TextAlertAction(type: .destructiveAction, title: "Удалить", action: { [weak self] in
                    self?.confirmRemoval(post)
                }),
                TextAlertAction(type: .genericAction, title: "Отмена", action: {})
            ], actionLayout: .vertical
        ), in: .window(.root))
    }

    private func confirmRemoval(_ post: VisualGramChannelPost) {
        self.controller?.present(textAlertController(
            context: self.context, title: "Удалить пост?", text: "Пост исчезнет из этого визуального канала.",
            actions: [
                TextAlertAction(type: .genericAction, title: "Отмена", action: {}),
                TextAlertAction(type: .destructiveAction, title: "Удалить", action: { [weak self] in
                    guard let self else { return }
                    let removed = VisualGramLocalAppearance.shared.removeVisualChannelPost(
                        accountId: self.context.account.peerId, sourcePeerId: self.sourcePeerId, postId: post.id
                    )
                    if !removed { self.showError("Не удалось удалить пост.") }
                })
            ]
        ), in: .window(.root))
    }

    func openEditor(post: VisualGramChannelPost?) {
        guard let copy = self.copy else { return }
        let current = post.flatMap { target in copy.posts.first(where: { $0.id == target.id }) }
        guard post == nil || current != nil else {
            self.showError("Этот пост уже удалён.")
            return
        }
        let actions = VisualGramChannelPostsActions(context: self.context, sourcePeerId: self.sourcePeerId, text: current?.text ?? "")
        let signal = combineLatest(self.context.sharedContext.presentationData, actions.draft.get(), VisualGramLocalAppearance.shared.changes)
        |> deliverOnMainQueue
        |> map { (presentation, text, _) -> (ItemListControllerState, (ItemListNodeState, Any)) in
            let available = actions.copy != nil
            let textToSave = text.trimmingCharacters(in: .whitespacesAndNewlines)
            let right = ItemListNavigationButton(
                content: .text(current == nil ? "Опубликовать" : "Сохранить"), style: .bold,
                enabled: available && !textToSave.isEmpty && textToSave.utf16.count <= visualGramChannelPostLimit,
                action: { [weak postActions = actions] in postActions?.save(textToSave, postId: current?.id) }
            )
            let presentationData = ItemListPresentationData(presentation)
            let state = ItemListControllerState(
                presentationData: presentationData, title: .text(current == nil ? "Новый пост" : "Редактирование поста"),
                leftNavigationButton: nil, rightNavigationButton: right,
                backNavigationButton: ItemListBackButton(title: presentation.strings.Common_Back)
            )
            let entries: [VisualGramChannelPostsEntry] = [
                .init(stableId: .draft, section: 0, index: 0, content: .draft(text)),
                .init(stableId: .draftHelp, section: 0, index: 1, content: .note(
                    available ? "Пост сохранится на этом устройстве." : "Визуальный канал недоступен."
                ))
            ]
            let list = ItemListNodeState(presentationData: presentationData, entries: entries, style: .blocks,
                                        focusItemTag: VisualGramChannelPostRowTag.input, animateChanges: false)
            return (state, (list, actions))
        }
        let editor = ItemListController(context: self.context, state: signal)
        actions.controller = editor
        self.controller?.push(editor)
    }

    private func save(_ text: String, postId: UUID?) {
        guard let controller = self.controller, self.copy != nil else { return }
        let store = VisualGramLocalAppearance.shared
        let saved: Bool
        if let postId {
            saved = store.editVisualChannelPost(
                accountId: self.context.account.peerId, sourcePeerId: self.sourcePeerId, postId: postId, text: text
            )
        } else {
            saved = store.addVisualChannelPost(
                accountId: self.context.account.peerId, sourcePeerId: self.sourcePeerId, text: text,
                now: Int32(clamping: Int64(Date().timeIntervalSince1970))
            )
        }
        if saved {
            controller.view.endEditing(true)
            controller.dismiss()
        } else {
            self.showError("Не удалось сохранить пост.")
        }
    }

    private func showError(_ text: String) {
        self.controller?.present(textAlertController(
            context: self.context, title: nil, text: text,
            actions: [TextAlertAction(type: .defaultAction, title: "OK", action: {})]
        ), in: .window(.root))
    }
}

public func visualGramChannelPostsController(context: AccountContext, sourcePeerId: EnginePeer.Id) -> ViewController {
    let actions = VisualGramChannelPostsActions(context: context, sourcePeerId: sourcePeerId)
    let authorPeer = context.engine.data.get(TelegramEngine.EngineData.Item.Peer.Peer(id: context.account.peerId))
    let sourcePeer = context.engine.data.subscribe(TelegramEngine.EngineData.Item.Peer.Peer(id: sourcePeerId))
    let signal = combineLatest(context.sharedContext.presentationData, VisualGramLocalAppearance.shared.changes, authorPeer, sourcePeer)
    |> deliverOnMainQueue
    |> map { (presentation, _, ownPeer, originalPeer) -> (ItemListControllerState, (ItemListNodeState, Any)) in
        let presentationData = ItemListPresentationData(presentation)
        let copy = actions.copy
        let settings = copy.map { _ in
            ItemListNavigationButton(content: .text("Настройки"), style: .regular, enabled: true, action: { [weak settingsActions = actions] in
                settingsActions?.openSettings()
            })
        }
        let state = ItemListControllerState(
            presentationData: presentationData, title: .text(copy?.properties.title ?? "Визуальный канал"),
            leftNavigationButton: nil, rightNavigationButton: settings,
            backNavigationButton: ItemListBackButton(title: presentation.strings.Common_Back)
        )
        var entries: [VisualGramChannelPostsEntry] = []
        if let copy {
            let properties = copy.properties
            var metadata = ["Визуальный канал"]
            if let count = properties.subscriberCount {
                metadata.append(presentation.strings.Conversation_StatusSubscribers(count))
            }
            if let username = properties.username, !username.isEmpty {
                metadata.append(username.hasPrefix("@") ? username : "@" + username)
            }
            entries.append(.init(stableId: .overview, section: 0, index: 0, content: .overview(
                title: properties.title, subtitle: metadata.joined(separator: " · "), verified: properties.verified,
                color: properties.color, source: originalPeer
            )))
            if !properties.about.isEmpty {
                entries.append(.init(stableId: .description, section: 0, index: 1, content: .note(properties.about)))
            }
            entries.append(.init(stableId: .source, section: 0, index: 2, content: .source))
            entries.append(.init(stableId: .compose, section: 1, index: 0, content: .compose))
            entries.append(.init(stableId: .posts, section: 2, index: 0, content: .header("Посты")))
            if copy.posts.isEmpty {
                entries.append(.init(stableId: .empty, section: 2, index: 1, content: .note("Здесь появятся ваши посты.")))
            }
            let author = ownPeer?.displayTitle(strings: presentation.strings, displayOrder: presentation.nameDisplayOrder) ?? "Владелец"
            for (index, post) in copy.posts.reversed().enumerated() {
                let date = DateFormatter.localizedString(
                    from: Date(timeIntervalSince1970: TimeInterval(post.date)), dateStyle: .medium, timeStyle: .short
                )
                var details = date
                if properties.signaturesEnabled {
                    let label = properties.showAuthors ? "Автор" : "Подпись"
                    details = "\(label): \(author) · \(date)"
                }
                entries.append(.init(stableId: .post(post.id), section: 2, index: index + 1, content: .post(post, details: details)))
            }
        } else {
            entries.append(.init(stableId: .empty, section: 0, index: 0, content: .note("Визуальный канал недоступен.")))
        }
        return (state, (ItemListNodeState(presentationData: presentationData, entries: entries, style: .blocks), actions))
    }
    let controller = ItemListController(context: context, state: signal)
    actions.controller = controller
    return controller
}
