import AccountContext
import Display
import Foundation
import ItemListUI
import OverlayStatusController
import PresentationDataUtils
import SwiftSignalKit
import TelegramCore
import TelegramPresentationData
import UIKit

private enum VisualGramChannelQuery: Equatable {
    case username(String)
    case id(Int64)

    init?(_ input: String) {
        let value = input.trimmingCharacters(in: .whitespacesAndNewlines)
        if let number = Int64(value) {
            let botChannelOffset: Int64 = 1_000_000_000_000
            let id = number < -botChannelOffset ? -(number + botChannelOffset) : number
            guard (1...0x00ff_ffff_ffff_ffff).contains(id) else { return nil }
            self = .id(id)
        } else if let name = VisualGramCollectionImport.username(from: value) {
            self = .username(name)
        } else {
            return nil
        }
    }
}

private enum VisualGramChannelsAction: Hashable {
    case selectSubscribers
    case copyChannel
    case openCopy(Int64)
    case editSubscriberCount(Int64)
}

private struct VisualGramChannelsMenuEntry: ItemListNodeEntry {
    let stableId: VisualGramChannelsAction
    let position: Int
    let section: ItemListSectionId
    let title: String
    let label: String

    static func < (lhs: Self, rhs: Self) -> Bool {
        lhs.section == rhs.section ? lhs.position < rhs.position : lhs.section < rhs.section
    }

    func item(presentationData: ItemListPresentationData, arguments: Any) -> ListViewItem {
        let actions = arguments as! VisualGramChannelsMenuActions
        return ItemListDisclosureItem(presentationData: presentationData, title: self.title,
            label: self.label, sectionId: self.section, style: .blocks,
            action: { actions.open(self.stableId) })
    }
}

private final class VisualGramChannelsMenuActions {
    private let context: AccountContext
    private let store = VisualGramLocalAppearance.shared
    private let lookup = MetaDisposable()
    private var lookupToken: UUID?
    weak var controller: ItemListController?

    init(context: AccountContext) {
        self.context = context
    }

    deinit {
        self.lookup.dispose()
    }

    func open(_ action: VisualGramChannelsAction) {
        let accountId = self.context.account.peerId
        switch action {
        case .selectSubscribers:
            self.askForSource(copying: false)
        case .copyChannel:
            self.askForSource(copying: true)
        case let .openCopy(source):
            let sourceId = EnginePeer.Id(source)
            guard self.store.visualChannel(accountId: accountId, sourcePeerId: sourceId)?.isCopied == true else {
                self.message("Копия канала недоступна.")
                return
            }
            self.controller?.push(visualGramChannelPostsController(context: self.context, sourcePeerId: sourceId))
        case let .editSubscriberCount(source):
            let sourceId = EnginePeer.Id(source)
            guard let record = self.store.visualChannel(accountId: accountId, sourcePeerId: sourceId) else { return }
            self.editCount(sourceId: sourceId, initial: record.properties)
        }
    }

    private func askForSource(copying: Bool) {
        guard self.lookupToken == nil else { return }
        self.presentInput(title: copying ? "Скопировать канал" : "Выбор подписчиков",
                          message: nil, placeholder: "@юзернейм или ID канала", value: "",
                          keyboard: .default, action: "Найти") { [weak self] input in
            guard let self else { return }
            guard let query = VisualGramChannelQuery(input) else {
                self.message("Введи @юзернейм, числовой ID или ID канала в формате −100…")
                return
            }
            self.lookupSource(query, copying: copying)
        }
    }

    private func lookupSource(_ query: VisualGramChannelQuery, copying: Bool) {
        guard self.lookupToken == nil, let controller = self.controller else { return }
        let token = UUID()
        self.lookupToken = token
        let context = self.context
        let theme = context.sharedContext.currentPresentationData.with { $0 }.theme
        let progress = OverlayStatusController(theme: theme, type: .loading(cancelled: { [weak self] in
            guard let self, self.lookupToken == token else { return }
            self.lookupToken = nil
            self.lookup.set(nil)
        }))
        controller.present(progress, in: .window(.root))

        let resolve: Signal<EnginePeer?, NoError>
        switch query {
        case let .username(name):
            resolve = context.engine.peers.resolvePeerByName(name: name, referrer: nil)
            |> filter { if case .result = $0 { return true }; return false }
            |> map { if case let .result(peer) = $0 { return peer }; return nil }
            |> take(1)
            |> timeout(12.0, queue: .mainQueue(), alternate: .single(nil))
        case let .id(id):
            let sourceId = EnginePeer.Id(namespace: Namespaces.Peer.CloudChannel, id: ._internalFromInt64Value(id))
            resolve = context.engine.data.get(TelegramEngine.EngineData.Item.Peer.Peer(id: sourceId))
        }

        let source = resolve
        |> mapToSignal { peer -> Signal<(EnginePeer.Id, VisualGramChannelProperties)?, NoError> in
            guard let peer, case let .channel(channel) = peer, case let .broadcast(broadcast) = channel.info else {
                return .single(nil)
            }
            return context.engine.peers.fetchAndUpdateCachedPeerData(peerId: peer.id)
            |> then(.single(false))
            |> take(1)
            |> timeout(6.0, queue: .mainQueue(), alternate: .single(false))
            |> mapToSignal { _ in
                context.engine.data.get(TelegramEngine.EngineData.Item.Peer.CachedData(id: peer.id))
            }
            |> map { cached in
                let data = cached as? CachedChannelData
                return (peer.id, VisualGramChannelProperties(
                    title: channel.title, about: data?.about ?? "", username: peer.addressName,
                    subscriberCount: data?.participantsSummary.memberCount, verified: channel.flags.contains(.isVerified),
                    signaturesEnabled: broadcast.flags.contains(.messagesShouldHaveSignatures),
                    showAuthors: broadcast.flags.contains(.messagesShouldHaveProfiles),
                    color: channel.nameColor?.rawValue
                ))
            }
        }
        |> then(.single(nil))
        |> take(1)
        |> deliverOnMainQueue

        self.lookup.set(source.start(next: { [weak self, weak progress] result in
            guard let self, self.lookupToken == token else { return }
            self.lookupToken = nil
            progress?.dismiss()
            guard let (sourceId, properties) = result else {
                switch query {
                case .id:
                    self.message("Канал с таким ID не найден на устройстве. Сначала открой канал или укажи его @юзернейм.")
                case .username:
                    self.message("Канал не найден. Проверь @юзернейм и подключение.")
                }
                return
            }
            if copying {
                self.confirmCopy(sourceId: sourceId, initial: properties)
            } else {
                self.editCount(sourceId: sourceId, initial: properties)
            }
        }))
    }

    private func confirmCopy(sourceId: EnginePeer.Id, initial: VisualGramChannelProperties) {
        let accountId = self.context.account.peerId
        if self.store.visualChannel(accountId: accountId, sourcePeerId: sourceId)?.isCopied == true {
            self.open(.openCopy(sourceId.toInt64()))
            return
        }
        let alert = textAlertController(context: self.context, title: "Скопировать канал?",
            text: "«\(initial.title)» появится в разделе «Каналы». Посты копии видны на этом устройстве.", actions: [
                TextAlertAction(type: .genericAction, title: "Отмена", action: {}),
                TextAlertAction(type: .defaultAction, title: "Скопировать", action: { [weak self] in
                    guard let self else { return }
                    guard self.store.copyVisualChannel(accountId: accountId, sourcePeerId: sourceId, initial: initial) else {
                        self.message("Не удалось сохранить копию канала.")
                        return
                    }
                    self.open(.openCopy(sourceId.toInt64()))
                })
            ])
        self.controller?.present(alert, in: .window(.root))
    }

    private func editCount(sourceId: EnginePeer.Id, initial: VisualGramChannelProperties) {
        let accountId = self.context.account.peerId
        let current = self.store.visualChannel(accountId: accountId, sourcePeerId: sourceId)?.subscriberCountOverride
        self.presentInput(title: "Количество подписчиков", message: "«\(initial.title)»\nПустое поле возвращает число Telegram.",
                          placeholder: "Количество подписчиков", value: current.map(String.init) ?? "",
                          keyboard: .numberPad, action: "Сохранить") { [weak self] input in
            guard let self else { return }
            let digits = input.filter { !$0.isWhitespace }
            let count: Int32?
            if digits.isEmpty {
                count = nil
            } else if digits.utf8.allSatisfy({ (48...57).contains($0) }), let value = Int32(digits) {
                count = value
            } else {
                self.message("Введи целое число от 0 до 2 147 483 647.")
                return
            }
            guard self.store.setVisualChannelSubscriberCount(accountId: accountId, sourcePeerId: sourceId,
                                                              count: count, initial: initial) else {
                self.message("Не удалось сохранить количество подписчиков.")
                return
            }
        }
    }

    private func message(_ text: String) {
        self.controller?.present(textAlertController(context: self.context, title: nil, text: text,
            actions: [TextAlertAction(type: .defaultAction, title: "ОК", action: {})]), in: .window(.root))
    }

    private func presentInput(title: String, message: String?, placeholder: String, value: String,
                              keyboard: UIKeyboardType, action: String, complete: @escaping (String) -> Void) {
        guard let controller = self.controller else { return }
        let alert = UIAlertController(title: title, message: message, preferredStyle: .alert)
        let theme = self.context.sharedContext.currentPresentationData.with { $0 }.theme
        alert.overrideUserInterfaceStyle = theme.overallDarkAppearance ? .dark : .light
        alert.addTextField { field in
            field.placeholder = placeholder
            field.text = value
            field.autocapitalizationType = .none
            field.autocorrectionType = .no
            field.keyboardType = keyboard
            field.keyboardAppearance = theme.overallDarkAppearance ? .dark : .light
        }
        alert.addAction(UIAlertAction(title: "Отмена", style: .cancel))
        alert.addAction(UIAlertAction(title: action, style: .default, handler: { [weak alert] _ in
            let text = alert?.textFields?.first?.text ?? ""
            DispatchQueue.main.async { [weak alert] in
                guard let alert, alert.presentingViewController != nil else {
                    complete(text)
                    return
                }
                if let coordinator = alert.transitionCoordinator,
                    coordinator.animate(alongsideTransition: nil, completion: { _ in complete(text) }) {
                    return
                }
                alert.dismiss(animated: true, completion: { complete(text) })
            }
        }))
        var presenter = controller.navigationController?.view.window?.rootViewController ?? controller
        while let presented = presenter.presentedViewController {
            presenter = presented
        }
        presenter.present(alert, animated: true)
    }
}

func visualGramChannelsMenuController(context: AccountContext) -> ViewController {
    let actions = VisualGramChannelsMenuActions(context: context)
    let store = VisualGramLocalAppearance.shared
    let signal = combineLatest(context.sharedContext.presentationData, store.changes)
    |> deliverOnMainQueue
    |> map { presentationData, _ -> (ItemListControllerState, (ItemListNodeState, Any)) in
        var entries = [
            VisualGramChannelsMenuEntry(stableId: .selectSubscribers, position: 0, section: 0, title: "Выбор подписчиков", label: ""),
            VisualGramChannelsMenuEntry(stableId: .copyChannel, position: 1, section: 0, title: "Скопировать канал", label: "")
        ]
        for channel in store.visualChannels(accountId: context.account.peerId) {
            if channel.isCopied {
                entries.append(.init(stableId: .openCopy(channel.sourcePeerId), position: entries.count, section: 1,
                                     title: channel.properties.title, label: "Копия"))
            } else if let count = channel.subscriberCountOverride {
                let label = NumberFormatter.localizedString(from: NSNumber(value: count), number: .decimal)
                entries.append(.init(stableId: .editSubscriberCount(channel.sourcePeerId), position: entries.count, section: 2,
                                     title: channel.properties.title, label: label))
            }
        }
        entries.sort()
        let state = ItemListControllerState(presentationData: ItemListPresentationData(presentationData), title: .text("Каналы"),
            leftNavigationButton: nil, rightNavigationButton: nil,
            backNavigationButton: ItemListBackButton(title: presentationData.strings.Common_Back))
        let list = ItemListNodeState(presentationData: ItemListPresentationData(presentationData), entries: entries, style: .blocks, animateChanges: false)
        return (state, (list, actions))
    }
    let controller = ItemListController(context: context, state: signal)
    actions.controller = controller
    return controller
}
