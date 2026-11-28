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
    case profileChannel
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
        self.askForSource(action)
    }

    private func askForSource(_ action: VisualGramChannelsAction) {
        guard self.lookupToken == nil else { return }
        let selected = action == .profileChannel ? self.store.profileChannel(accountId: self.context.account.peerId) : nil
        self.presentInput(title: action == .profileChannel ? "Канал в профиле" : "Количество подписчиков",
                          message: selected == nil ? nil : "Пустое поле возвращает канал из настроек Telegram.",
                          placeholder: "@юзернейм или ID канала", value: selected.map { String($0.id._internalGetInt64Value()) } ?? "",
                          keyboard: .default, action: "Найти") { [weak self] input in
            guard let self else { return }
            if action == .profileChannel, selected != nil, input.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                self.saveProfileChannel(nil, replacing: selected)
                return
            }
            guard let query = VisualGramChannelQuery(input) else {
                self.message("Введи @юзернейм, числовой ID или ID канала в формате −100…")
                return
            }
            self.lookupSource(query, action: action, previous: selected)
        }
    }

    private func lookupSource(_ query: VisualGramChannelQuery, action: VisualGramChannelsAction, previous: EnginePeer.Id?) {
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
            |> mapToSignal { cached in
                if let cached { return .single(cached) }
                return context.engine.peers.findChannelById(channelId: id)
                |> timeout(12.0, queue: .mainQueue(), alternate: .single(nil))
            }
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
                    self.message("Канал с таким ID недоступен. Проверь ID или укажи @юзернейм.")
                case .username:
                    self.message("Канал не найден. Проверь @юзернейм и подключение.")
                }
                return
            }
            if action == .profileChannel {
                self.confirmProfileChannel(sourceId: sourceId, title: properties.title, previous: previous)
            } else {
                self.editCount(sourceId: sourceId, initial: properties)
            }
        }))
    }

    private func confirmProfileChannel(sourceId: EnginePeer.Id, title: String, previous: EnginePeer.Id?) {
        let alert = textAlertController(context: self.context, title: "Канал в профиле",
            text: "Показывать «\(title)» в твоём профиле?", actions: [
                TextAlertAction(type: .genericAction, title: "Отмена", action: {}),
                TextAlertAction(type: .defaultAction, title: "Показать", action: { [weak self] in
                    self?.saveProfileChannel(sourceId, replacing: previous)
                })
            ])
        self.controller?.present(alert, in: .window(.root))
    }

    private func saveProfileChannel(_ sourceId: EnginePeer.Id?, replacing previous: EnginePeer.Id?) {
        guard self.store.setProfileChannel(accountId: self.context.account.peerId, channelId: sourceId, replacing: previous) else {
            self.message("Не удалось сохранить канал профиля.")
            return
        }
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
    let signal = context.sharedContext.presentationData
    |> deliverOnMainQueue
    |> map { presentationData -> (ItemListControllerState, (ItemListNodeState, Any)) in
        let entries = [
            VisualGramChannelsMenuEntry(stableId: .selectSubscribers, position: 0, section: 0, title: "Количество подписчиков", label: ""),
            VisualGramChannelsMenuEntry(stableId: .profileChannel, position: 1, section: 0, title: "Канал в профиле", label: "")
        ]
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
