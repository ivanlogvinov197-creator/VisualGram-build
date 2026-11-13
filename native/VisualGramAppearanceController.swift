import Foundation
import UIKit
import Display
import SwiftSignalKit
import TelegramCore
import TelegramPresentationData
import PresentationDataUtils
import ItemListUI
import AccountContext
import GiftOptionsScreen
import GiftViewScreen
import GiftCraftScreen
import EntityKeyboard
import EmojiStatusSelectionComponent
import ChatScheduleTimeController
import ConfettiEffect
import PeerNameColorScreen
import BusinessHoursSetupScreen
import BusinessLocationSetupScreen

private struct VisualGramAppearanceEntry: ItemListNodeEntry {
    enum Kind: Equatable { case toggle(Bool), button(String), destructive, info }
    let stableId: Int32
    let section: ItemListSectionId
    let title: String
    let kind: Kind
    let theme: PresentationTheme

    static func ==(lhs: Self, rhs: Self) -> Bool {
        return lhs.stableId == rhs.stableId && lhs.section == rhs.section && lhs.title == rhs.title && lhs.kind == rhs.kind && lhs.theme === rhs.theme
    }

    static func <(lhs: Self, rhs: Self) -> Bool {
        func rank(_ id: Int32) -> Int32 { switch id { case 24: return 18; case 23: return 21; case 27: return 25; default: return id } }
        return lhs.section == rhs.section ? rank(lhs.stableId) < rank(rhs.stableId) : lhs.section < rhs.section
    }

    func item(presentationData: ItemListPresentationData, arguments: Any) -> ListViewItem {
        let actions = arguments as! VisualGramAppearanceActions
        switch self.kind {
        case let .toggle(value):
            return ItemListSwitchItem(presentationData: presentationData, title: self.title, value: value, sectionId: self.section, style: .blocks, updated: { actions.toggle(self.stableId, value: $0) })
        case let .button(label):
            return ItemListDisclosureItem(presentationData: presentationData, title: self.title, label: label, sectionId: self.section, style: .blocks, action: { actions.open(self.stableId) })
        case .destructive:
            return ItemListActionItem(presentationData: presentationData, title: self.title, kind: .destructive, alignment: .natural, sectionId: self.section, style: .blocks, action: { actions.open(self.stableId) })
        case .info:
            return ItemListTextItem(presentationData: presentationData, text: .plain(self.title), sectionId: self.section)
        }
    }
}

private final class VisualGramAppearanceActions {
    let context: AccountContext
    weak var controller: ItemListController?
    let disposables = DisposableSet()
    let activeSection = ValuePromise<Int32>(-1, ignoreRepeated: true)
    let expandedLists = ValuePromise<Int32>(-1, ignoreRepeated: true)
    private var expandedListBits: Int32 = 0
    var targetPeerId: EnginePeer.Id
    var targetTitle = "Мой профиль"
    private var counterpartyId: Int64?
    private var direction: VisualGramGift.Direction = .received
    private var giftDate = Int32(Date().timeIntervalSince1970)
    private var giftText = ""

    init(context: AccountContext) { self.context = context; self.targetPeerId = context.account.peerId }
    deinit { self.disposables.dispose() }

    var appearance: VisualGramAppearance { return VisualGramLocalAppearance.shared.appearance(accountId: self.context.account.peerId, targetPeerId: self.targetPeerId) }
    private var scheduledGifts: [VisualGramScheduledGift] {
        return VisualGramLocalAppearance.shared.pendingScheduledGifts.filter { $0.targetPeerId == self.targetPeerId.toInt64() }.sorted { $0.deliveryDate < $1.deliveryDate }
    }

    private func presentNative(_ alert: UIAlertController) {
        let theme = self.context.sharedContext.currentPresentationData.with { $0 }.theme
        alert.overrideUserInterfaceStyle = theme.overallDarkAppearance ? .dark : .light
        for field in alert.textFields ?? [] {
            field.keyboardAppearance = theme.overallDarkAppearance ? .dark : .light
        }
        var presenter: UIViewController? = self.controller?.navigationController?.view.window?.rootViewController ?? self.controller
        while let presented = presenter?.presentedViewController { presenter = presented }
        presenter?.present(alert, animated: true)
    }

    func update(_ f: (inout VisualGramAppearance) -> Void) {
        VisualGramLocalAppearance.shared.update(accountId: self.context.account.peerId, targetPeerId: self.targetPeerId, f)
    }

    func toggle(_ id: Int32, value: Bool) {
        guard VisualGramActivation.shared.hasAccess else { self.openActivation(); return }
        if id == 3 {
            if value { self.configureVerification() } else { self.update { $0.verification = nil } }
            return
        }
        self.update {
            switch id {
            case 0: $0.enabled = value
            case 1: $0.premium = value; $0.enabled = true
            case 2: $0.verified = value; $0.enabled = true
            default: break
            }
        }
    }

    func toggleList(_ bit: Int32) {
        self.expandedListBits ^= bit
        self.expandedLists.set(self.expandedListBits)
    }

    func message(_ text: String) {
        let alert = UIAlertController(title: "DuckGram", message: text, preferredStyle: .alert)
        alert.addAction(UIAlertAction(title: "OK", style: .default))
        self.presentNative(alert)
    }

    func openActivation() {
        let activation = VisualGramActivation.shared
        let alert = UIAlertController(title: "Доступ к DuckGram", message: activation.statusText + "\n\nПробный период — 24 часа. Код активирует доступ на одном устройстве. Для проверки нужен интернет. Настройки сохраняются при блокировке.", preferredStyle: .alert)
        alert.addAction(UIAlertAction(title: "Закрыть", style: .cancel))
        alert.addAction(UIAlertAction(title: "Купить доступ в боте", style: .default, handler: { [weak self] _ in
            guard let self, let controller = self.controller else { return }
            self.context.sharedContext.openExternalUrl(context: self.context, urlContext: .generic, url: "https://t.me/duckkgrambot", forceExternal: false, presentationData: self.context.sharedContext.currentPresentationData.with { $0 }, navigationController: controller.navigationController as? NavigationController, dismissInput: {})
        }))
        alert.addAction(UIAlertAction(title: "Проверить доступ", style: .default, handler: { [weak self] _ in
            activation.refresh { [weak self] error in self?.message(error ?? activation.statusText) }
        }))
        alert.addAction(UIAlertAction(title: "Ввести код", style: .default, handler: { [weak self] _ in
            guard let self = self else { return }
            let input = UIAlertController(title: "Код активации", message: "Код будет привязан к этому устройству.", preferredStyle: .alert)
            input.addTextField { field in
                field.placeholder = "XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX"
                field.autocapitalizationType = .allCharacters
                field.autocorrectionType = .no
                field.spellCheckingType = .no
            }
            input.addAction(UIAlertAction(title: "Отмена", style: .cancel))
            input.addAction(UIAlertAction(title: "Активировать", style: .default, handler: { [weak self, weak input] _ in
                guard let code = input?.textFields?.first?.text, !code.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { self?.message("Введите код активации."); return }
                activation.refresh(code: code) { [weak self] error in self?.message(error ?? activation.statusText) }
            }))
            self.presentNative(input)
        }))
        self.presentNative(alert)
    }

    func form(title: String, fields: [(String, String)], save: @escaping ([String]) -> Void) {
        let alert = UIAlertController(title: title, message: nil, preferredStyle: .alert)
        for (placeholder, value) in fields {
            alert.addTextField { field in
                field.placeholder = placeholder
                field.text = value
                field.autocapitalizationType = .none
                field.autocorrectionType = .no
            }
        }
        alert.addAction(UIAlertAction(title: "Отмена", style: .cancel))
        alert.addAction(UIAlertAction(title: "Сохранить", style: .default, handler: { [weak alert] _ in
            save(alert?.textFields?.map { $0.text?.trimmingCharacters(in: .whitespacesAndNewlines) ?? "" } ?? [])
        }))
        self.presentNative(alert)
    }

    private var dateFormatter: DateFormatter {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.dateFormat = "yyyy-MM-dd HH:mm"
        return formatter
    }

    private func minorAmount(_ text: String, scale: Decimal) -> Int64? {
        guard let value = Decimal(string: text.replacingOccurrences(of: ",", with: "."), locale: Locale(identifier: "en_US_POSIX")), value >= 0 else { return nil }
        let result = value * scale
        guard result <= Decimal(Int64.max) else { return nil }
        return NSDecimalNumber(decimal: result).int64Value
    }

    func open(_ id: Int32) {
        if id == 1000 { self.openActivation(); return }
        guard VisualGramActivation.shared.hasAccess else { self.openActivation(); return }
        if (900...902).contains(id) { self.activeSection.set(id - 900); return }

        switch id {
        case 3: self.configureVerification()
        case 4: self.selectEmoji()
        case 5:
            self.update { $0.overridesEmojiStatus = true; $0.emojiStatus = nil }
        case 7: self.selectTarget()
        case 8: self.configureVerification(forceSetup: true)
        case 10: self.editUsername(index: nil)
        case 11: self.editPhone()
        case 12: self.editRating()
        case 13: self.openUsernames()
        case 26: self.openGiftList(history: true)
        case 20:
            self.direction = .received; self.counterpartyId = nil; self.giftDate = Int32(clamping: Int64(Date().timeIntervalSince1970)); self.giftText = ""
            self.selectOrdinaryGift()
        case 21: self.configureReceipt { [weak self] in self?.importUniqueGift() }
        case 22: self.configureReceipt(direction: .sent) { [weak self] in self?.selectOrdinaryGift() }
        case 23: self.configureReceipt(direction: .sent) { [weak self] in self?.importUniqueGift() }
        case 24:
            self.direction = .received
            self.counterpartyId = nil
            self.giftDate = Int32(Date().timeIntervalSince1970)
            self.giftText = ""
            self.importUniqueGift()
        case 14:
            self.controller?.push(UserAppearanceScreen(context: self.context, visualGramTarget: self.targetPeerId))
        case 15:
            self.controller?.push(BusinessHoursSetupScreen(context: self.context, initialValue: self.appearance.businessHours, completion: { _ in }, visualGramTarget: self.targetPeerId))
        case 16:
            self.controller?.push(BusinessLocationSetupScreen(context: self.context, initialValue: self.appearance.businessLocation, completion: { _ in }, visualGramTarget: self.targetPeerId))
        case 27: self.openGiftList(history: false)
        case 903: self.activeSection.set(-1)
        case 32:
            self.form(title: "Баланс GRAM", fields: [("GRAM", self.appearance.grams.map { VisualGramLocalAppearance.formatGrams($0) } ?? "")]) { [weak self] values in
                guard let self, values.count == 1 else { return }
                if values[0].isEmpty { self.update { $0.grams = nil }; return }
                guard let balance = VisualGramLocalAppearance.parseGrams(values[0]) else { self.message("Введите баланс: до 9 знаков после запятой."); return }
                self.update {
                    let delta = balance - ($0.grams ?? 0)
                    var history = $0.gramHistory ?? []
                    if delta != 0 { history.append(.init(id: UUID().uuidString, date: Int32(clamping: Int64(Date().timeIntervalSince1970)), amount: delta, kind: delta > 0 ? .topUp : .adjustment, title: nil, peerId: nil, gift: nil)) }
                    $0.grams = balance; $0.gramHistory = history; $0.enabled = true
                }
            }
        case 33: self.controller?.push(VisualGramCardEditorController(context: self.context, target: self.targetPeerId))
        case 34: self.openBalanceHistory(.stars)
        case 35: self.openBalanceHistory(.grams)
        case 30:
            self.form(title: "Баланс звёзд", fields: [("Баланс", self.appearance.stars.map(String.init) ?? "")]) { [weak self] values in
                guard let self, values.count == 1 else { return }
                if values[0].isEmpty { self.update { $0.stars = nil }; return }
                guard let stars = Int64(values[0]), stars >= 0 else { self.message("Введите целое число от 0 до \(Int64.max)"); return }
                self.update {
                    let previous = $0.stars ?? 0
                    let delta = stars - previous
                    VisualGramLocalAppearance.recordStarsTransaction(value: &$0, amount: delta, kind: delta > 0 ? .topUp : .adjustment, peerId: nil, gift: nil, now: Int32(clamping: Int64(Date().timeIntervalSince1970)))
                    $0.stars = stars; $0.enabled = true
                }
            }
        case 31:
            self.form(title: "Добавить операцию", fields: [("Звёзды: +100 или -25", ""), ("Дата: ГГГГ-ММ-ДД ЧЧ:ММ", self.dateFormatter.string(from: Date()))]) { [weak self] values in
                guard let self, values.count == 2, let amount = Int64(values[0]), amount != 0, let date = self.dateFormatter.date(from: values[1]) else { self?.message("Проверь сумму и дату"); return }
                let current = self.appearance.stars ?? 0
                let (balance, overflow) = current.addingReportingOverflow(amount)
                guard !overflow, balance >= 0 else { self.message("Недостаточно звёзд"); return }
                self.update {
                    $0.enabled = true; $0.stars = balance
                    VisualGramLocalAppearance.recordStarsTransaction(value: &$0, amount: amount, kind: amount > 0 ? .topUp : .adjustment, peerId: nil, gift: nil, now: Int32(clamping: Int64(date.timeIntervalSince1970)))
                }
            }
        case 40:
            let accountId = self.context.account.peerId
            let targetPeerId = self.targetPeerId
            let alert = textAlertController(
                context: self.context,
                title: "Очистить всё оформление?",
                text: "Профиль «\(self.targetTitle)». Будут удалены локальные настройки, подарки, балансы и история. Отложенные подарки этого профиля будут отменены.",
                actions: [
                    TextAlertAction(type: .genericAction, title: "Отмена", action: {}),
                    TextAlertAction(type: .destructiveAction, title: "Очистить", action: {
                        VisualGramLocalAppearance.shared.reset(accountId: accountId, targetPeerId: targetPeerId)
                    })
                ],
                dismissOnOutsideTap: false
            )
            self.controller?.present(alert, in: .window(.root))
        case 1000..<2000: self.editUsername(index: Int(id - 1000))
        case 2000..<3000: self.openGift(index: Int(id - 2000))
        case 3000..<4000: self.openScheduledGift(index: Int(id - 3000))
        default: break
        }
    }

    private func usdAmount(ton: Int64) -> Int64? {
        guard let rate = self.context.currentAppConfiguration.with({ $0 }).data?["ton_usd_rate"] as? Double, rate.isFinite, rate > 0 else { return nil }
        var amount = Decimal(ton) / 1_000_000_000 * Decimal(rate) * 100
        var rounded = Decimal(); NSDecimalRound(&rounded, &amount, 0, .plain)
        guard rounded >= 0, rounded <= Decimal(Int64.max) else { return nil }
        return NSDecimalNumber(decimal: rounded).int64Value
    }

    private func resolvePerson(_ input: String, completion: @escaping (EnginePeer?) -> Void) {
        let value = input.trimmingCharacters(in: .whitespacesAndNewlines)
        if let raw = Int64(value), raw > 0 {
            self.disposables.add((self.context.engine.data.get(TelegramEngine.EngineData.Item.Peer.Peer(id: EnginePeer.Id(raw))) |> deliverOnMainQueue).start(next: { peer in
                if let peer, case .user = peer { completion(peer) } else { completion(nil) }
            }))
        } else {
            let name = value.trimmingCharacters(in: CharacterSet(charactersIn: "@"))
            self.disposables.add((self.context.engine.peers.resolvePeerByName(name: name, referrer: nil) |> deliverOnMainQueue).start(next: { result in
                guard case let .result(peer) = result else { return }
                if let peer, case .user = peer { completion(peer) } else { completion(nil) }
            }))
        }
    }

    private func editUsername(index: Int?) {
        let item = index.flatMap { self.appearance.usernames.indices.contains($0) ? self.appearance.usernames[$0] : nil }
        let originalName = item?.name
        self.controller?.push(VisualGramDetailsController(context: self.context, title: "NFT-юзернейм", fields: [("Юзернейм без @", item?.name ?? ""), ("Цена TON", item.map { VisualGramLocalAppearance.formatGrams($0.tonAmount) } ?? "")], date: item?.purchaseDate ?? Int32(clamping: Int64(Date().timeIntervalSince1970)), tonIndex: 1, save: { [weak self] texts, date in
            guard let self, texts.count == 2 else { return false }
            let name = texts[0].trimmingCharacters(in: CharacterSet(charactersIn: "@ "))
            guard name.range(of: "^[A-Za-z][A-Za-z0-9_]{3,31}$", options: .regularExpression) != nil, let ton = VisualGramLocalAppearance.parseGrams(texts[1]), let usd = self.usdAmount(ton: ton) else { self.message("Проверь юзернейм и цену. Для расчёта USDT нужен загруженный курс TON."); return false }
            guard !self.appearance.usernames.contains(where: { $0.name.lowercased() == name.lowercased() && $0.name.lowercased() != originalName?.lowercased() }) else { self.message("Этот юзернейм уже добавлен."); return false }
            if let originalName, !self.appearance.usernames.contains(where: { $0.name == originalName }) { self.message("Этот юзернейм уже удалён."); return false }
            let username = VisualGramUsername(name: name, purchaseDate: date, tonAmount: ton, usdAmount: usd)
            self.update { value in
                value.enabled = true
                if let originalName, let position = value.usernames.firstIndex(where: { $0.name == originalName }) { value.usernames[position] = username }
                else { value.usernames.append(username) }
            }
            return true
        }))
    }

    private func selectTarget() {
        self.form(title: "Чей профиль оформить", fields: [("@юзернейм или ID (пусто — мой профиль)", self.targetPeerId == self.context.account.peerId ? "" : String(self.targetPeerId.toInt64()))]) { [weak self] texts in
            guard let self, let input = texts.first else { return }
            if input.isEmpty {
                self.targetPeerId = self.context.account.peerId; self.targetTitle = "Мой профиль"
                VisualGramLocalAppearance.shared.update(accountId: self.context.account.peerId) { _ in }; return
            }
            self.resolvePerson(input) { [weak self] peer in
                guard let self, let peer else { self?.message("Профиль не найден. Для неизвестного ID сначала открой чат с человеком или укажи @юзернейм."); return }
                self.targetPeerId = peer.id; self.targetTitle = peer.compactDisplayTitle
                VisualGramLocalAppearance.shared.update(accountId: self.context.account.peerId) { _ in }
            }
        }
    }

    private func editPhone() {
        let item = self.appearance.phoneNumber
        self.controller?.push(VisualGramDetailsController(context: self.context, title: "Номер профиля", fields: [("Номер: +7… или +888…", item.map { "+" + $0.name } ?? ""), ("Цена TON", item.map { VisualGramLocalAppearance.formatGrams($0.tonAmount) } ?? "")], date: item?.purchaseDate ?? Int32(clamping: Int64(Date().timeIntervalSince1970)), tonIndex: 1, phoneMode: true, save: { [weak self] texts, date in
            guard let self, texts.count == 2 else { return false }
            if texts[0].isEmpty { self.update { $0.phoneNumber = nil }; return true }
            let number = texts[0].filter { $0.isNumber }
            guard number.range(of: "^[0-9]{5,15}$", options: .regularExpression) != nil else { self.message("Проверь номер."); return false }
            var ton: Int64 = 0, usd: Int64 = 0
            if number.hasPrefix("888") {
                guard let price = VisualGramLocalAppearance.parseGrams(texts[1]), let dollar = self.usdAmount(ton: price) else { self.message("Проверь цену и подключение для загрузки курса TON."); return false }
                ton = price; usd = dollar
            }
            self.update { $0.enabled = true; $0.phoneNumber = VisualGramUsername(name: number, purchaseDate: date, tonAmount: ton, usdAmount: usd) }
            return true
        }))
    }

    private func editRating() {
        let appearance = self.appearance
        let now = Int64(Date().timeIntervalSince1970)
        let savedPending = appearance.pendingStarRating
        let pending = savedPending.flatMap { Int64($0.timestamp) > now ? $0 : nil }
        let rating = pending == nil ? savedPending?.rating ?? appearance.starRating : appearance.starRating
        let fields: [(String, String)] = [
            ("Уровень в профиле. Пустое поле вернёт настоящий рейтинг.", rating.map { String($0.level) } ?? ""),
            ("Баллы на начало уровня. Отсюда заполняется полоска. Пусто — от нуля.", rating.map { String($0.currentLevelStars) } ?? ""),
            ("Текущие баллы. Число слева от дроби.", rating.map { String($0.stars) } ?? ""),
            ("Порог следующего уровня. Число справа от дроби. Пусто — без порога.", rating?.nextLevelStars.map(String.init) ?? ""),
            ("Через сколько дней обновится рейтинг. 0 — сегодня, пусто — без обновления.", pending.map {
                let remaining = Int64($0.timestamp) - now
                return String(remaining < 86400 ? 0 : (remaining + 86399) / 86400)
            } ?? ""),
            ("Сколько баллов добавится при обновлении.", pending.flatMap { future in rating.map { String(future.rating.stars - $0.stars) } } ?? "")
        ]
        let target = self.targetPeerId
        self.controller?.push(VisualGramDetailsController(context: self.context, title: "Рейтинг Telegram", fields: fields, date: nil, showFieldLabels: true, save: { [weak self] inputs, _ in
            guard let self, inputs.count == 6 else { return false }
            let values = inputs.map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            if values[0].isEmpty {
                VisualGramLocalAppearance.shared.update(accountId: self.context.account.peerId, targetPeerId: target) {
                    $0.starRating = nil
                    $0.pendingStarRating = nil
                }
                return true
            }
            let next = Int64(values[3])
            guard let level = Int32(values[0]), (-1...1_000_000).contains(level),
                  let stars = Int64(values[2]), stars != Int64.min,
                  let start = values[1].isEmpty ? min(0, stars) : Int64(values[1]),
                  start <= stars, values[3].isEmpty || next != nil,
                  (level < 0 ? stars < 0 && (next.map { $0 <= 0 } ?? true) : start >= 0),
                  next.map({ $0 > stars }) ?? true else {
                self.message("Начало уровня должно быть не выше текущих баллов, а следующий порог — выше них. Для отрицательного рейтинга укажи уровень −1 и отрицательные баллы.")
                return false
            }
            var pendingRating: TelegramStarPendingRating?
            if !values[4].isEmpty || !values[5].isEmpty {
                guard let days = Int64(values[4]), (0...365).contains(days),
                      let points = Int32(values[5]), points > 0 else {
                    self.message("Для обновления укажи срок от 0 до 365 дней и положительное число баллов.")
                    return false
                }
                let (futureStars, overflow) = stars.addingReportingOverflow(Int64(points))
                let timestamp = Int64(Date().timeIntervalSince1970) + (days == 0 ? 3600 : days * 86400)
                guard !overflow, let updateTime = Int32(exactly: timestamp) else {
                    self.message("Проверь баллы и срок обновления.")
                    return false
                }
                let reachedNextLevel = next.map { futureStars >= $0 } ?? false
                let future = TelegramStarRating(level: reachedNextLevel ? level + 1 : level,
                    currentLevelStars: reachedNextLevel ? (next ?? start) : start,
                    stars: futureStars, nextLevelStars: reachedNextLevel ? nil : next)
                pendingRating = TelegramStarPendingRating(rating: future, timestamp: updateTime)
            }
            VisualGramLocalAppearance.shared.update(accountId: self.context.account.peerId, targetPeerId: target) {
                $0.enabled = true
                $0.starRating = TelegramStarRating(level: level, currentLevelStars: start, stars: stars, nextLevelStars: next)
                $0.pendingStarRating = pendingRating
            }
            return true
        }))
    }

    private func configureVerification(forceSetup: Bool = false) {
        let target = self.targetPeerId
        let alert = UIAlertController(title: "Верификация", message: nil, preferredStyle: .alert)
        for (title, source) in [("Major", "starsov"), ("Hold", "hold")] {
            alert.addAction(UIAlertAction(title: title, style: .default, handler: { [weak self] _ in
                guard let self else { return }
                self.resolvePerson(source) { [weak self] peer in
                    guard let self, let peer else { self?.message("Не удалось загрузить @" + source); return }
                    self.disposables.add((self.context.engine.peers.fetchAndUpdateCachedPeerData(peerId: peer.id)
                    |> mapToSignal { _ in self.context.engine.data.get(TelegramEngine.EngineData.Item.Peer.CachedData(id: peer.id)) }
                    |> deliverOnMainQueue).start(next: { [weak self] cached in
                        guard let self else { return }
                        let template: PeerVerification
                        if let existing = (cached as? CachedUserData)?.verification { template = existing }
                        else if let settings = (cached as? CachedUserData)?.botInfo?.verifierSettings { template = PeerVerification(botId: peer.id, iconFileId: settings.iconFileId, description: settings.customDescription ?? settings.companyName, descriptionEntities: settings.customDescriptionEntities ?? []) }
                        else { self.message("Исходный значок @" + source + " сейчас недоступен."); return }
                        VisualGramLocalAppearance.shared.update(accountId: self.context.account.peerId, targetPeerId: target) { $0.enabled = true; $0.verification = template; $0.verificationSource = source }
                    }))
                }
            }))
        }
        alert.addAction(UIAlertAction(title: "Выключить", style: .destructive, handler: { [weak self] _ in
            guard let self else { return }
            VisualGramLocalAppearance.shared.update(accountId: self.context.account.peerId, targetPeerId: target) { $0.verification = nil; $0.verificationSource = nil }
        }))
        alert.addAction(UIAlertAction(title: "Отмена", style: .cancel)); self.presentNative(alert)
    }

    private func selectEmoji() {
        guard let controller = self.controller else { return }
        self.update { $0.enabled = true; $0.premium = true }
        let current = self.appearance.emojiStatus?.fileId
        let picker = EmojiStatusSelectionController(context: self.context, mode: .customStatusSelection(completion: { [weak self] file, expiration in
            guard let self else { return }
            _ = VisualGramLocalAppearance.shared.setLocalEmojiStatus(accountId: self.context.account.peerId, targetPeerId: self.targetPeerId, status: file.map { PeerEmojiStatus(content: .emoji(fileId: $0.fileId.id), expirationDate: expiration) })
        }), sourceView: controller.view, emojiContent: EmojiPagerContentComponent.emojiInputData(context: self.context, animationCache: self.context.animationCache, animationRenderer: self.context.animationRenderer, isStandalone: false, subject: .status, hasTrending: false, topReactionItems: [], areUnicodeEmojiEnabled: false, areCustomEmojiEnabled: true, chatPeerId: self.context.account.peerId, selectedItems: [], topStatusTitle: nil, forceHasPremium: true), currentSelection: current, destinationItemView: { nil })
        picker.pushController = { [weak controller] in controller?.push($0) }
        controller.present(picker, in: .window(.root))
    }

    private func configureReceipt(direction: VisualGramGift.Direction = .received, completion: @escaping () -> Void) {
        let target = self.targetPeerId
        self.direction = direction
        weak var details: ViewController?
        let form = VisualGramDetailsController(context: self.context, title: direction == .sent ? "Отправить подарок" : "Добавить подарок", fields: [(direction == .sent ? "Получатель: @юзернейм или ID" : "Отправитель: @юзернейм или ID", ""), ("Подпись", "")], date: Int32(clamping: Int64(Date().timeIntervalSince1970)), seconds: true, save: { [weak self] texts, date in
            guard let self, self.targetPeerId == target, texts.count == 2 else { return false }
            self.giftDate = date; self.giftText = texts[1]
            if texts[0].isEmpty && direction == .received { self.counterpartyId = nil; details?.dismiss(); completion(); return false }
            self.resolvePerson(texts[0]) { [weak self] peer in
                guard let self, self.targetPeerId == target, let peer else { self?.message("Пользователь не найден или выбран другой профиль."); return }
                self.counterpartyId = peer.id.toInt64(); details?.dismiss(); completion()
            }
            return false
        })
        details = form; self.controller?.push(form)
    }

    private func selectOrdinaryGift() {
        guard let controller = self.controller, let stars = self.context.starsContext else { return }
        let options = GiftOptionsScreen(context: self.context, starsContext: stars, peerId: self.targetPeerId, premiumOptions: [], hasBirthday: false)
        options.visualGramGiftSelected = { [weak self] gift in
            self?.previewGift(gift)
        }
        controller.push(options)
    }

    private func importUniqueGift() {
        self.form(title: "Добавить NFT-подарки", fields: [("Ссылки или slug через пробел или новую строку", "")]) { [weak self] values in
            guard let self, let input = values.first else { return }
            guard let slugs = VisualGramLocalAppearance.nftSlugs(from: input) else { self.message("Вставь до 100 ссылок t.me/nft/… или slug, например PlushPepe-1. Раздели их пробелами или переносами строк."); return }
            let targetPeerId = self.targetPeerId
            let counterpartyId = self.counterpartyId, direction = self.direction, date = self.giftDate, text = self.giftText
            // Resolve in order, without opening a preview for each link. A failed link
            // aborts the batch before any profile or queue changes are committed.
            var signal: Signal<[StarGift.UniqueGift], GetUniqueStarGiftError> = .single([])
            for slug in slugs {
                signal = signal |> mapToSignal { [context = self.context] gifts in
                    context.engine.payments.getUniqueStarGift(slug: slug) |> map { gifts + [$0] }
                }
            }
            self.disposables.add((signal |> deliverOnMainQueue).start(next: { [weak self] gifts in
                guard let self else { return }
                let batch = gifts.map { VisualGramGift(gift: .unique($0), counterpartyId: counterpartyId, direction: direction, date: date, text: text) }
                guard let first = batch.first else { return }
                self.chooseGiftDelivery(first) { [weak self] deliveryDate in
                    guard let self else { return }
                    if batch.count == 1 {
                        DispatchQueue.main.asyncAfter(deadline: .now() + 0.35) { [weak self] in self?.showGiftPreview(first, targetPeerId: targetPeerId, deliveryDate: deliveryDate) }
                        return
                    }
                    if let deliveryDate {
                        VisualGramLocalAppearance.shared.scheduleGifts(accountId: self.context.account.peerId, targetPeerId: targetPeerId, gifts: batch, deliveryDate: deliveryDate)
                    } else {
                        VisualGramLocalAppearance.shared.addGifts(accountId: self.context.account.peerId, targetPeerId: targetPeerId, gifts: batch)
                        self.animateGiftDelivery()
                    }
                }
            }, error: { [weak self] _ in self?.message("Не удалось загрузить все подарки. Проверь ссылки и подключение; ни один подарок не добавлен.") }))
        }
    }

    private func previewGift(_ gift: StarGift) {
        let local = VisualGramGift(gift: gift, counterpartyId: self.counterpartyId, direction: self.direction, date: self.giftDate, text: self.giftText)
        let targetPeerId = self.targetPeerId
        self.chooseGiftDelivery(local) { [weak self] deliveryDate in
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.35) {
                self?.showGiftPreview(local, targetPeerId: targetPeerId, deliveryDate: deliveryDate)
            }
        }
    }

    private func showGiftPreview(_ local: VisualGramGift, targetPeerId: EnginePeer.Id, deliveryDate: Int32?) {
        guard let controller = self.controller else { return }
        let subject: GiftViewScreen.Subject
        switch local.gift {
        case let .unique(value): subject = .uniqueGift(value, nil)
        case let .generic(value): subject = .soldOutGift(value)
        }
        let title = deliveryDate == nil ? (local.direction == .sent ? "Отправить" : "Получить") : "Отложить"
        let preview = GiftViewScreen(context: self.context, subject: subject, customAction: .init(title: title, action: { [weak self] in
            guard let self else { return }
            if let deliveryDate {
                VisualGramLocalAppearance.shared.scheduleGift(accountId: self.context.account.peerId, targetPeerId: targetPeerId, gift: local, deliveryDate: deliveryDate)
            } else {
                self.deliverGift(local, targetPeerId: targetPeerId)
            }
        }))
        preview.visualGramPreview = true
        controller.push(preview)
    }

    private func deliverGift(_ gift: VisualGramGift, targetPeerId: EnginePeer.Id) {
        VisualGramLocalAppearance.shared.addGift(accountId: self.context.account.peerId, targetPeerId: targetPeerId, gift: gift)
        self.animateGiftDelivery()
    }

    private func animateGiftDelivery() {
        guard !UIAccessibility.isReduceMotionEnabled, let view = self.controller?.navigationController?.view ?? self.controller?.view, view.window != nil else { return }
        view.addSubview(ConfettiView(frame: view.bounds))
    }

    private func chooseGiftDelivery(_ gift: VisualGramGift, completion: @escaping (Int32?) -> Void) {
        if gift.date > Int32(clamping: Int64(Date().timeIntervalSince1970)) { completion(gift.date); return }
        let receiving = gift.direction == .received
        let alert = UIAlertController(title: receiving ? "Получить подарок" : "Отправить подарок", message: nil, preferredStyle: .alert)
        alert.addAction(UIAlertAction(title: receiving ? "Получить сейчас" : "Отправить сейчас", style: .default, handler: { _ in completion(nil) }))
        alert.addAction(UIAlertAction(title: receiving ? "Отложить получение" : "Отложить отправку", style: .default, handler: { [weak self] _ in
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.35) { self?.pickDeliveryDate(currentTime: nil) { time in
                completion(time)
            } }
        }))
        alert.addAction(UIAlertAction(title: "Отмена", style: .cancel))
        self.presentNative(alert)
    }

    private func pickDeliveryDate(currentTime: Int32?, completion: @escaping (Int32) -> Void) {
        self.controller?.push(VisualGramDetailsController(context: self.context, title: "Дата и время", fields: [], date: currentTime ?? Int32(clamping: Int64(Date().timeIntervalSince1970)) + 60, seconds: true, save: { [weak self] _, time in
            guard time > Int32(clamping: Int64(Date().timeIntervalSince1970)), time < Int32.max - 1 else { self?.message("Выбери время в будущем."); return false }
            completion(time); return true
        }))
    }

    private func openScheduledGift(index: Int) {
        let queue = self.scheduledGifts
        guard queue.indices.contains(index) else { return }
        let pending = queue[index]
        let alert = UIAlertController(title: "Отложенный подарок", message: self.dateFormatter.string(from: Date(timeIntervalSince1970: TimeInterval(pending.deliveryDate))), preferredStyle: .alert)
        alert.addAction(UIAlertAction(title: pending.gift.direction == .received ? "Получить сейчас" : "Отправить сейчас", style: .default, handler: { _ in
            VisualGramLocalAppearance.shared.rescheduleGift(id: pending.id, deliveryDate: Int32(clamping: Int64(Date().timeIntervalSince1970)))
        }))
        alert.addAction(UIAlertAction(title: "Изменить время", style: .default, handler: { [weak self] _ in
            DispatchQueue.main.async { self?.pickDeliveryDate(currentTime: pending.deliveryDate) { time in
                VisualGramLocalAppearance.shared.rescheduleGift(id: pending.id, deliveryDate: time)
            } }
        }))
        alert.addAction(UIAlertAction(title: pending.gift.direction == .received ? "Отменить получение" : "Отменить отправку", style: .destructive, handler: { _ in
            VisualGramLocalAppearance.shared.cancelScheduledGift(id: pending.id)
        }))
        alert.addAction(UIAlertAction(title: "Назад", style: .cancel))
        self.presentNative(alert)
    }

    private func openUsernames() {
        let target = self.targetPeerId, account = self.context.account.peerId
        self.controller?.push(VisualGramListController(context: self.context, target: target, title: "Юзернеймы", rows: {
            VisualGramLocalAppearance.shared.appearance(accountId: account, targetPeerId: target).usernames.map { .init(id: $0.name.lowercased(), title: "@" + $0.name, subtitle: VisualGramLocalAppearance.formatGrams($0.tonAmount) + " TON", gift: nil) }
        }, reorder: { ids in
            var saved = false
            VisualGramLocalAppearance.shared.update(accountId: account, targetPeerId: target) { value in
                guard ids.count == value.usernames.count, Set(ids).count == ids.count, Set(ids) == Set(value.usernames.map { $0.name.lowercased() }) else { return }
                value.usernames = ids.compactMap { id in value.usernames.first(where: { $0.name.lowercased() == id }) }; saved = true
            }
            return saved
        }, open: { [weak self] id in self?.editUsernameNamed(id) }, edit: { [weak self] id in self?.editUsernameNamed(id) }, delete: { id in
            VisualGramLocalAppearance.shared.update(accountId: account, targetPeerId: target) { $0.usernames.removeAll { $0.name.lowercased() == id } }
        }))
    }

    private func editUsernameNamed(_ id: String) {
        guard let index = self.appearance.usernames.firstIndex(where: { $0.name.lowercased() == id }) else { return }
        self.editUsername(index: index)
    }

    private func openBalanceHistory(_ currency: VisualGramBalanceHistory) {
        let store = VisualGramLocalAppearance.shared
        let account = self.context.account.peerId
        let target = self.targetPeerId
        let grams = currency == .grams
        let unit = grams ? "GRAM" : "★"
        let formatter = DateFormatter()
        formatter.dateFormat = "dd.MM.yyyy HH:mm:ss"
        let entries: () -> [VisualGramGift.StarsTransaction] = {
            currency.displayedEntries(in: store.appearance(accountId: account, targetPeerId: target), editorOrder: true)
        }
        let formatAmount: (Int64) -> String = { amount in
            let text = grams ? VisualGramLocalAppearance.formatGrams(amount) : String(amount)
            return amount > 0 ? "+" + text : text
        }
        let edit: (String) -> Void = { [weak self] id in
            guard let self, let entry = entries().first(where: { $0.id == id }) else { return }
            let form = VisualGramDetailsController(context: self.context, title: "Изменить операцию", fields: [
                ("Сумма · " + unit, formatAmount(entry.amount)),
                ("Комментарий", entry.comment ?? "")
            ], date: entry.date, seconds: true, showFieldLabels: true, save: { [weak self] fields, date in
                guard let self, fields.count == 2 else { return false }
                let input = fields[0].trimmingCharacters(in: .whitespacesAndNewlines)
                let magnitude = input.hasPrefix("-") || input.hasPrefix("+") ? String(input.dropFirst()) : input
                let amount = grams ? VisualGramLocalAppearance.parseGrams(magnitude) : Int64(magnitude)
                guard let amount, amount > 0 else { self.message("Введи сумму больше нуля."); return false }
                let signed = input.hasPrefix("-") || (!input.hasPrefix("+") && entry.amount < 0) ? -amount : amount
                guard (signed < 0) == (entry.amount < 0) else { self.message("У операции должен остаться исходный знак суммы."); return false }
                let comment = fields[1].trimmingCharacters(in: .whitespacesAndNewlines)
                let edit = VisualGramGift.StarsTransaction.HistoryEdit(amount: signed, date: date, comment: comment.isEmpty ? nil : comment)
                guard store.editBalanceHistoryEntry(target: target, currency: currency, id: id, edit: edit) else {
                    self.message("Операция больше недоступна.")
                    return false
                }
                return true
            })
            self.controller?.push(form)
        }
        self.controller?.push(VisualGramListController(context: self.context, target: target, title: grams ? "Мои операции GRAM" : "Мои операции звёзд", rows: {
            entries().map { entry in
                let title: String
                switch entry.kind {
                case .topUp: title = "Пополнение"
                case .purchase: title = "Покупка"
                case .sale: title = "Продажа"
                case .transfer: title = entry.amount < 0 ? "Исходящий перевод" : "Входящий перевод"
                case .adjustment: title = entry.amount < 0 ? "Списание" : "Начисление"
                }
                let date = formatter.string(from: Date(timeIntervalSince1970: TimeInterval(entry.date)))
                let details = [date, entry.comment ?? entry.walletAddress ?? entry.peerId.map { "ID \($0)" }].compactMap { $0 }.joined(separator: "\n")
                let gift = entry.gift.map { VisualGramGift(gift: $0, counterpartyId: entry.peerId, date: entry.date, text: "") }
                return .init(id: entry.id, title: "\(formatAmount(entry.amount)) \(unit) · \(entry.title ?? title)", subtitle: details, gift: gift)
            }
        }, reorder: { ids in
            store.saveBalanceHistoryOrder(target: target, currency: currency, ids: ids)
        }, open: edit, edit: edit, delete: { [weak self] id in
            if !store.deleteBalanceHistoryEntry(target: target, currency: currency, id: id) {
                self?.message("Операция больше недоступна.")
            }
        }, deleteConfirmation: "Запись исчезнет из истории баланса. Сумма на балансе не изменится."))
    }

    private func openGiftList(history: Bool) {
        guard history else { self.showGiftList(history: false, names: [:]); return }
        let operations = VisualGramLocalAppearance.giftOperations(in: self.appearance)
        let ids = Set(operations.flatMap { self.operationParticipants($0).compactMap { $0 } })
        self.loadOperationNames(ids: ids) { [weak self] names in self?.showGiftList(history: true, names: names) }
    }

    private func operationParticipants(_ item: VisualGramGift) -> [Int64?] {
        if item.operationEventId != nil { return [item.operationSenderId, item.operationRecipientId] }
        if item.direction == .sent { return [self.targetPeerId.toInt64(), item.counterpartyId] }
        return [item.counterpartyId, self.targetPeerId.toInt64()]
    }

    private func loadOperationNames(ids: Set<Int64>, completion: @escaping ([Int64: String]) -> Void) {
        guard !ids.isEmpty else { completion([:]); return }
        self.disposables.add((self.context.engine.data.get(EngineDataMap(ids.map { TelegramEngine.EngineData.Item.Peer.Peer(id: EnginePeer.Id($0)) })) |> deliverOnMainQueue).start(next: { peers in
            var names: [Int64: String] = [:]
            for (id, peer) in peers { if let peer { names[id.toInt64()] = peer.compactDisplayTitle } }
            completion(names)
        }))
    }

    private func operationTitle(_ item: VisualGramGift) -> String {
        switch item.operationKind {
        case .craft: return item.operationSucceeded == false ? "Крафт — неудача" : "Крафт"
        case .upgrade: return "Улучшение"
        case .purchase: return "Покупка"
        default: return item.direction == .sent ? "Отправка" : "Получение"
        }
    }

    private func showGiftList(history: Bool, names: [Int64: String]) {
        let target = self.targetPeerId, account = self.context.account.peerId
        let formatter = DateFormatter(); formatter.dateFormat = "dd.MM.yyyy HH:mm:ss"
        self.controller?.push(VisualGramListController(context: self.context, target: target, title: history ? "История операций" : "Мои подарки", rows: { [weak self] in
            guard let self else { return [] }
            let value = VisualGramLocalAppearance.shared.appearance(accountId: account, targetPeerId: target)
            let gifts = history ? VisualGramLocalAppearance.giftOperations(in: value) : VisualGramLocalAppearance.orderedOwnedGifts(in: value)
            var rows: [VisualGramListRow] = gifts.map { local in
                let title: String
                switch local.gift { case let .unique(gift): title = "\(gift.title) #\(gift.number)"; case let .generic(gift): title = gift.title ?? "Подарок" }
                let operation = self.operationTitle(local)
                let people = self.operationParticipants(local)
                let name: (Int64?) -> String = { id in id.map { names[$0] ?? "ID \($0)" } ?? "Не указан" }
                let parties = local.operationKind == .craft || local.operationKind == .upgrade ? "" : "\(name(people[0])) → \(name(people[1]))\n"
                return .init(id: local.identifier, title: history ? operation + " · " + title : title, subtitle: (history ? parties : "") + formatter.string(from: Date(timeIntervalSince1970: TimeInterval(local.date))), gift: local)
            }
            if history {
                for pending in VisualGramLocalAppearance.shared.pendingScheduledGifts where pending.targetPeerId == target.toInt64() {
                    let title: String
                    switch pending.gift.gift { case let .unique(gift): title = "\(gift.title) #\(gift.number)"; case let .generic(gift): title = gift.title ?? "Подарок" }
                    rows.append(.init(id: "pending:" + pending.id, title: title, subtitle: "Отложено · " + formatter.string(from: Date(timeIntervalSince1970: TimeInterval(pending.deliveryDate))), gift: pending.gift))
                }
            }
            return rows
        }, reorder: history ? nil : { ids in VisualGramLocalAppearance.shared.saveGiftOrder(accountId: account, targetPeerId: target, identifiers: ids) }, open: { [weak self] id in
            guard let self else { return }
            if history { self.openOperation(id) }
            else if let index = self.appearance.gifts.firstIndex(where: { $0.identifier == id }) { self.openGift(index: index) }
        }, edit: { [weak self] id in self?.editGiftDetails(id: id, history: history) }, delete: { [weak self] id in
            if id.hasPrefix("pending:") { VisualGramLocalAppearance.shared.cancelScheduledGift(id: String(id.dropFirst(8))) }
            else if history {
                switch VisualGramLocalAppearance.shared.cancelGiftOperation(accountId: account, targetPeerId: target, identifier: id) {
                case .success: break
                case .legacyUnavailable: self?.message("Эта запись создана старой версией без снимка для отмены. Точно восстановить её состояние невозможно; запись не удалена.")
                case .dependentOperation: self?.message("Подарок уже изменён, передан или использован в следующей операции. Сначала отмени более позднюю операцию.")
                case .balanceChanged: self?.message("Для отмены недостаточно текущего баланса либо изменились данные покупки. Сначала отмени зависимые покупки.")
                default: self?.message("Операция недоступна или её данные изменились. Ничего не отменено.")
                }
            } else { VisualGramLocalAppearance.shared.removeLocalGifts(accountId: account, targetPeerId: target, identifiers: [id]) }
        }, deleteTitle: history ? "Отменить операцию" : "Удалить", deleteConfirmation: history ? "Операция будет отменена: связанные подарки и списания будут восстановлены. Запись исчезнет у всех её участников. Если есть зависимые действия, сначала нужно отменить их." : nil))
    }

    private func operation(_ id: String, history: Bool) -> VisualGramGift? {
        if id.hasPrefix("pending:") { return self.scheduledGifts.first(where: { $0.id == String(id.dropFirst(8)) })?.gift }
        return history ? VisualGramLocalAppearance.giftOperations(in: self.appearance).first(where: { $0.identifier == id }) : self.appearance.gifts.first(where: { $0.identifier == id && $0.isHistoryOnly != true && $0.direction == .received })
    }

    private func openOperation(_ id: String) {
        guard let local = self.operation(id, history: true) else { return }
        if id.hasPrefix("pending:") { self.editGiftDetails(id: id, history: true); return }
        let participants = self.operationParticipants(local)
        let ids = Set(participants.compactMap { $0 })
        let target = self.targetPeerId
        self.loadOperationNames(ids: ids) { [weak self] names in
            guard let self else { return }
            let name: (Int64?) -> String = { id in id.map { names[$0] ?? "ID \($0)" } ?? "Не указан" }
            var rows: [VisualGramListRow] = []
            let formatter = DateFormatter(); formatter.dateFormat = "dd.MM.yyyy HH:mm:ss"
            rows.append(.init(id: "event", title: self.operationTitle(local), subtitle: formatter.string(from: Date(timeIntervalSince1970: TimeInterval(local.date))), gift: nil))
            if local.operationKind == .craft || local.operationKind == .upgrade {
                rows.append(.init(id: "owner", title: "Профиль", subtitle: name(participants[1]), gift: nil))
            } else {
                rows.append(.init(id: "from", title: local.operationKind == .purchase ? "Покупатель" : "От кого", subtitle: name(participants[0]), gift: nil))
                rows.append(.init(id: "to", title: "Кому", subtitle: name(participants[1]), gift: nil))
            }
            func addGift(_ gift: StarGift, title: String, id: String) {
                let label: String
                switch gift { case let .unique(gift): label = "\(gift.title) #\(gift.number)"; case let .generic(gift): label = gift.title ?? "Подарок" }
                let preview = VisualGramGift(gift: gift, counterpartyId: nil, date: local.date, text: "")
                rows.append(.init(id: id, title: title, subtitle: label, gift: preview))
            }
            for (index, gift) in (local.operationInputs ?? []).enumerated() { addGift(gift, title: local.operationKind == .upgrade ? "До улучшения" : "Использован NFT", id: "input:\(index)") }
            if local.operationKind == .craft && local.operationEventId == nil {
                rows.append(.init(id: "legacy", title: "Старая запись", subtitle: "Полный состав и результат этой операции не сохранялись старой версией.", gift: nil))
                if local.isCrafted == true { addGift(local.gift, title: "Сохранённый результат", id: "result") }
            } else if local.operationKind == .craft && local.operationSucceeded == false {
                rows.append(.init(id: "failed", title: "Результат: неудача", subtitle: "Новый NFT не получен. Выбранные подарки израсходованы.", gift: nil))
            } else { addGift(local.operationResult ?? local.gift, title: local.operationKind == .upgrade ? "После улучшения" : "Результат", id: "result") }
            if !local.text.isEmpty { rows.append(.init(id: "caption", title: "Подпись", subtitle: local.text, gift: nil)) }
            self.controller?.push(VisualGramListController(context: self.context, target: target, title: "Операция", rows: { rows }, reorder: nil, open: { _ in }, edit: { _ in }, delete: { _ in }, allowsEditing: false))
        }
    }

    private func editGiftDetails(id: String, history: Bool) {
        guard let local = self.operation(id, history: history) else { return }
        let target = self.targetPeerId
        let initialDate = id.hasPrefix("pending:") ? self.scheduledGifts.first(where: { $0.id == String(id.dropFirst(8)) })?.deliveryDate ?? local.date : local.date
        weak var details: ViewController?
        let form = VisualGramDetailsController(context: self.context, title: "Данные подарка", fields: [(local.direction == .sent ? "Получатель: @юзернейм или ID" : "Отправитель: @юзернейм или ID", local.counterpartyId.map(String.init) ?? ""), ("Подпись", local.text)], date: initialDate, seconds: true, save: { [weak self] texts, date in
            guard let self, texts.count == 2 else { return false }
            let apply: (Int64?) -> Void = { [weak self] person in
                guard let self else { return }
                if id.hasPrefix("pending:") {
                    guard date > Int32(clamping: Int64(Date().timeIntervalSince1970)) else { self.message("Выбери время в будущем."); return }
                    var gift = local; gift.counterpartyId = person; gift.date = date; gift.text = texts[1]
                    VisualGramLocalAppearance.shared.editScheduledGift(id: String(id.dropFirst(8)), gift: gift, deliveryDate: date)
                } else {
                    guard VisualGramLocalAppearance.shared.editGiftDetails(accountId: self.context.account.peerId, targetPeerId: target, identifier: id, history: history, counterpartyId: person, date: date, text: texts[1]) else { self.message("Запись изменилась или у получателя уже есть этот NFT."); return }
                }
                details?.dismiss()
            }
            if texts[0].isEmpty { apply(nil) }
            else { self.resolvePerson(texts[0]) { [weak self] peer in guard let peer else { self?.message("Пользователь не найден."); return }; apply(peer.id.toInt64()) } }
            return false
        })
        details = form; self.controller?.push(form)
    }

    private func openGift(index: Int) {
        guard self.appearance.gifts.indices.contains(index), self.controller != nil else { return }
        let local = self.appearance.gifts[index]
            let show: (EnginePeer?) -> Void = { [weak self] sender in
                guard let self else { return }
                let screen: GiftViewScreen
                if local.direction == .sent {
                    let subject: GiftViewScreen.Subject
                    switch local.displayGift(accountId: self.targetPeerId) {
                    case let .unique(gift): subject = .uniqueGift(gift, nil)
                    case let .generic(gift): subject = .soldOutGift(gift)
                    }
                    screen = GiftViewScreen(context: self.context, subject: subject, customAction: .init(title: "Удалить", action: { [weak self] in
                        guard let self else { return }
                        VisualGramLocalAppearance.shared.removeLocalGifts(accountId: self.context.account.peerId, targetPeerId: self.targetPeerId, identifiers: [local.identifier])
                    }))
                    screen.visualGramPreview = true
                } else {
                    screen = GiftViewScreen(context: self.context, subject: .profileGift(self.targetPeerId, local.profileGift(accountId: self.targetPeerId, sender: sender)))
                }
                self.controller?.push(screen)
            }
            if let senderId = local.counterpartyId {
                self.disposables.add((self.context.engine.data.get(TelegramEngine.EngineData.Item.Peer.Peer(id: EnginePeer.Id(senderId))) |> deliverOnMainQueue).start(next: show))
            } else { show(nil) }
    }

}

func visualGramAppearanceController(context: AccountContext) -> ViewController {
    VisualGramActivation.shared.start(vendorIdentifier: UIDevice.current.identifierForVendor?.uuidString, isForeground: UIApplication.shared.applicationState != .background, activeNotification: UIApplication.didBecomeActiveNotification, backgroundNotification: UIApplication.didEnterBackgroundNotification)
    let actions = VisualGramAppearanceActions(context: context)
    let signal = combineLatest(context.sharedContext.presentationData, VisualGramLocalAppearance.shared.changes, actions.expandedLists.get(), actions.activeSection.get())
    |> deliverOnMainQueue
    |> map { presentationData, _, _, activeSection -> (ItemListControllerState, (ItemListNodeState, Any)) in
        let value = actions.appearance
        var entries: [VisualGramAppearanceEntry] = []
        func add(_ id: Int32, _ section: Int32, _ title: String, _ kind: VisualGramAppearanceEntry.Kind) {
            entries.append(VisualGramAppearanceEntry(stableId: id, section: section, title: title, kind: kind, theme: presentationData.theme))
        }
        if !VisualGramActivation.shared.hasAccess {
            add(1000, 0, "Активация DuckGram", .button("Введите код"))
        } else {
        if activeSection == -1 { add(1000, -2, "Доступ", .button("Проверить")) }
        add(7, -1, "Выбор профиля", .button(actions.targetTitle))
        if activeSection == -1 {
            add(900, 0, "Профиль", .button("")); add(901, 0, "Подарки", .button("")); add(902, 0, "Балансы", .button(""))
            add(40, 1, "Очистить всё оформление", .destructive)
        } else {
            add(903, -1, "Назад", .button(""))
            switch activeSection {
            case 0:
                add(1, 0, "Telegram Premium", .toggle(value.premium))
                add(2, 0, "Галочка Telegram", .toggle(value.verified))
                add(3, 0, "Верификация", .button(value.verification == nil ? "Выключена" : (value.verificationSource == "hold" ? "Hold" : "Major")))
                add(10, 1, "Добавить NFT-юзернейм", .button(""))
                add(11, 1, "Номер профиля", .button(value.phoneNumber.map { "+" + $0.name } ?? ""))
                add(12, 1, "Уровень", .button(value.starRating.map { String($0.level) } ?? "Настоящий"))
                add(13, 1, "Юзернеймы", .button(String(value.usernames.count)))
                add(14, 2, "Цвета и фон профиля", .button(""))
                add(15, 2, "Часы работы", .button("")); add(16, 2, "Адрес", .button(""))
            case 1:
                add(24, 0, "Добавить NFT", .button("")); add(20, 0, "Добавить обычный подарок", .button(""))
                add(23, 1, "Отправить NFT", .button("")); add(22, 1, "Отправить обычный подарок", .button(""))
                add(27, 2, "Мои подарки", .button("")); add(26, 2, "История операций", .button(""))
            default:
                add(30, 0, "Баланс звёзд", .button(value.stars.map(String.init) ?? "Настоящий баланс"))
                add(31, 0, "Добавить операцию", .button(""))
                add(34, 0, "Мои операции звёзд", .button(""))
                add(32, 1, "Баланс GRAM", .button(value.grams.map { VisualGramLocalAppearance.formatGrams($0) } ?? "Не задан"))
                add(33, 1, "Оформить карточку GRAM", .button(""))
                add(35, 1, "Мои операции GRAM", .button(""))
            }
        }
        }
        entries.sort()
        let controllerState = ItemListControllerState(presentationData: ItemListPresentationData(presentationData), title: .text(activeSection == -1 ? "DuckGram" : ["Профиль", "Подарки", "Балансы"][Int(activeSection)]), leftNavigationButton: nil, rightNavigationButton: nil, backNavigationButton: ItemListBackButton(title: presentationData.strings.Common_Back))
        let listState = ItemListNodeState(presentationData: ItemListPresentationData(presentationData), entries: entries, style: .blocks, animateChanges: false)
        return (controllerState, (listState, actions))
    }
    let controller = ItemListController(context: context, state: signal)
    actions.controller = controller
    return controller
}
