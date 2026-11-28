import Foundation
import Display
import SwiftSignalKit
import TelegramCore
import TelegramPresentationData
import AccountContext
import ItemListUI
import StatisticsUI

private struct VisualGramStarsStatisticsEntry: ItemListNodeEntry {
    enum Content: Equatable {
        case header(String)
        case graph(StatsGraph)
        case value(String, String)
    }

    let stableId: Int32
    let section: ItemListSectionId
    let content: Content

    static func < (lhs: Self, rhs: Self) -> Bool {
        lhs.stableId < rhs.stableId
    }

    func item(presentationData: ItemListPresentationData, arguments: Any) -> ListViewItem {
        switch self.content {
        case let .header(text):
            return ItemListSectionHeaderItem(presentationData: presentationData, text: text, multiline: true, sectionId: self.section)
        case let .graph(graph):
            return StatsGraphItem(presentationData: presentationData, graph: graph, type: .bars, noInitialZoom: true, sectionId: self.section, style: .blocks)
        case let .value(title, label):
            return ItemListDisclosureItem(presentationData: presentationData, title: title, label: label, sectionId: self.section, style: .blocks, disclosureStyle: .none, action: nil)
        }
    }
}

func visualGramStarsStatisticsScreen(context: AccountContext) -> ViewController {
    let store = VisualGramLocalAppearance.shared
    let accountId = context.account.peerId
    let signal = combineLatest(context.sharedContext.presentationData, store.changes)
    |> deliverOnMainQueue
    |> map { presentationData, _ -> (ItemListControllerState, (ItemListNodeState, Any)) in
        let now = Int32(clamping: Int64(Date().timeIntervalSince1970))
        let stats = VisualGramStarsStatistics(appearance: store.appearance(accountId: accountId), now: now)
        let listPresentationData = ItemListPresentationData(presentationData)
        var entries: [VisualGramStarsStatisticsEntry] = []
        if let stats {
            entries.append(.init(stableId: 0, section: 0, content: .header("ПОСТУПЛЕНИЯ ЗА 365 ДНЕЙ")))
            if let graph = stats.incomingGraph {
                entries.append(.init(stableId: 1, section: 0, content: .graph(graph)))
            } else {
                entries.append(.init(stableId: 1, section: 0, content: .value("За этот период поступлений нет", "")))
            }
            func stars(_ count: Int64) -> String {
                "⭐ " + NumberFormatter.localizedString(from: NSNumber(value: count), number: .decimal)
            }
            entries.append(.init(stableId: 2, section: 1, content: .header("ВИЗУАЛЬНЫЙ БАЛАНС")))
            entries.append(.init(stableId: 3, section: 1, content: .value("Текущий баланс", stars(stats.balance))))
            entries.append(.init(stableId: 4, section: 1, content: .value("Всего поступило", stars(stats.received))))
            entries.append(.init(stableId: 5, section: 1, content: .value("Всего потрачено", stars(stats.spent))))
            entries.append(.init(stableId: 6, section: 1, content: .value("Операции", String(stats.operations))))
        } else {
            entries.append(.init(stableId: 0, section: 0, content: .header("Баланс недоступен.")))
        }
        let controllerState = ItemListControllerState(presentationData: listPresentationData, title: .text("Статистика DuckGram"), leftNavigationButton: nil, rightNavigationButton: nil, backNavigationButton: ItemListBackButton(title: presentationData.strings.Common_Back))
        let listState = ItemListNodeState(presentationData: listPresentationData, entries: entries, style: .blocks, animateChanges: false)
        return (controllerState, (listState, Void()))
    }
    return ItemListController(context: context, state: signal)
}
