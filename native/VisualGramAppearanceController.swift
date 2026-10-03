import Foundation
import UIKit
import Display
import SwiftSignalKit
import TelegramCore
import TelegramPresentationData
import ItemListUI
import AccountContext
import GiftOptionsScreen
import GiftViewScreen
import EntityKeyboard
import EmojiStatusSelectionComponent
import ChatScheduleTimeController
import ConfettiEffect

private struct VisualGramAppearanceEntry: ItemListNodeEntry {
    enum Kind: Equatable { case toggle(Bool), button(String), info }
    let stableId: Int32
    let section: ItemListSectionId
    let title: String
    let kind: Kind
    let theme: PresentationTheme

    static func ==(lhs: Self, rhs: Self) -> Bool {
        return lhs.stableId == rhs.stableId && lhs.section == rhs.section && lhs.title == rhs.title && lhs.kind == rhs.kind && lhs.theme === rhs.theme
    }

    static func <(lhs: Self, rhs: Self) -> Bool {
        return lhs.section == rhs.section ? lhs.stableId < rhs.stableId : lhs.section < rhs.section
    }

    func item(presentationData: ItemListPresentationData, arguments: Any) -> ListViewItem {
        let actions = arguments as! VisualGramAppearanceActions
        switch self.kind {
        case let .toggle(value):
            return ItemListSwitchItem(presentationData: presentationData, title: self.title, value: value, sectionId: self.section, style: .blocks, updated: { actions.toggle(self.stableId, value: $0) })
        case let .button(label):
            return ItemListDisclosureItem(presentationData: presentationData, title: self.title, label: label, sectionId: self.section, style: .blocks, action: { actions.open(self.stableId) })
        case .info:
            return ItemListTextItem(presentationData: presentationData, text: .plain(self.title), sectionId: self.section)
        }
    }
}

private final class VisualGramAppearanceActions {
    let context: AccountContext
    weak var controller: ItemListController?
    let disposables = DisposableSet()
    let expandedLists = ValuePromise<Int32>(0, ignoreRepeated: true)
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
        var presenter: UIViewController? = self.controller?.navigationController?.view.window?.rootViewController ?? self.controller
        while let presented = presenter?.presentedViewController { presenter = presented }
        presenter?.present(alert, animated: true)
    }

    func update(_ f: (inout VisualGramAppearance) -> Void) {
        VisualGramLocalAppearance.shared.update(accountId: self.context.account.peerId, targetPeerId: self.targetPeerId, f)
    }

    func toggle(_ id: Int32, value: Bool) {
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
        let alert = UIAlertController(title: "VisualGram", message: text, preferredStyle: .alert)
        alert.addAction(UIAlertAction(title: "OK", style: .default))
        self.presentNative(alert)
    }

    func form(title: String, fields: [(String, String)], save: @escaping ([String]) -> Void) {
        let alert = UIAlertController(title: title, message: "Изменения видны только в этом клиенте", preferredStyle: .alert)
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
        case 13: self.toggleList(1)
        case 26: self.toggleList(2)
        case 20: self.configureReceipt { [weak self] in self?.selectOrdinaryGift() }
        case 21: self.configureReceipt { [weak self] in self?.importUniqueGift() }
        case 22: self.configureReceipt(direction: .sent) { [weak self] in self?.selectOrdinaryGift() }
        case 23: self.configureReceipt(direction: .sent) { [weak self] in self?.importUniqueGift() }
        case 24:
            self.direction = .received
            self.counterpartyId = nil
            self.giftDate = Int32(Date().timeIntervalSince1970)
            self.giftText = ""
            self.importUniqueGift()
        case 30:
            self.form(title: "Визуальный баланс звёзд", fields: [("Баланс", self.appearance.stars.map(String.init) ?? "")]) { [weak self] values in
                guard let self, values.count == 1 else { return }
                if values[0].isEmpty { self.update { $0.stars = nil }; return }
                guard let stars = Int64(values[0]), stars >= 0 else { self.message("Введите целое число от 0 до \(Int64.max)"); return }
                self.update { $0.stars = stars; $0.enabled = true }
            }
        case 40:
            let alert = UIAlertController(title: "Сбросить оформление?", message: "Локальные подарки, юзернеймы, номер, рейтинг, значки и статусы выбранного профиля будут удалены.", preferredStyle: .alert)
            alert.addAction(UIAlertAction(title: "Отмена", style: .cancel))
            alert.addAction(UIAlertAction(title: "Сбросить", style: .destructive, handler: { [weak self] _ in
                guard let self else { return }
                VisualGramLocalAppearance.shared.reset(accountId: self.context.account.peerId, targetPeerId: self.targetPeerId)
            }))
            self.presentNative(alert)
        case 1000..<2000: self.editUsername(index: Int(id - 1000))
        case 2000..<3000: self.openGift(index: Int(id - 2000))
        case 3000..<4000: self.openScheduledGift(index: Int(id - 3000))
        default: break
        }
    }

    private func editUsername(index: Int?) {
        let item = index.flatMap { self.appearance.usernames.indices.contains($0) ? self.appearance.usernames[$0] : nil }
        let date = self.dateFormatter.string(from: Date(timeIntervalSince1970: TimeInterval(item?.purchaseDate ?? Int32(Date().timeIntervalSince1970))))
        self.form(title: "NFT-юзернейм", fields: [("Юзернейм без @ (пусто — удалить)", item?.name ?? ""), ("Дата: yyyy-MM-dd HH:mm", date), ("Цена TON", item.map { String(Double($0.tonAmount) / 1_000_000_000) } ?? "100"), ("Стоимость USD", item.map { String(Double($0.usdAmount) / 100) } ?? "250")]) { [weak self] values in
            guard let self, values.count == 4 else { return }
            let name = values[0].trimmingCharacters(in: CharacterSet(charactersIn: "@"))
            if name.isEmpty, let index {
                self.update { if $0.usernames.indices.contains(index) { $0.usernames.remove(at: index) } }
                return
            }
            guard name.range(of: "^[A-Za-z][A-Za-z0-9_]{3,31}$", options: .regularExpression) != nil, let date = self.dateFormatter.date(from: values[1]), date.timeIntervalSince1970 >= 0, date.timeIntervalSince1970 <= Double(Int32.max), let ton = self.minorAmount(values[2], scale: 1_000_000_000), let usd = self.minorAmount(values[3], scale: 100) else {
                self.message("Проверь юзернейм, дату и неотрицательные цены."); return
            }
            let username = VisualGramUsername(name: name, purchaseDate: Int32(date.timeIntervalSince1970), tonAmount: ton, usdAmount: usd)
            self.update {
                $0.enabled = true
                if let index, $0.usernames.indices.contains(index) { $0.usernames[index] = username }
                else if !$0.usernames.contains(where: { $0.name.lowercased() == name.lowercased() }) { $0.usernames.append(username) }
            }
        }
    }

    private func selectTarget() {
        self.form(title: "Чей профиль оформить", fields: [("@юзернейм (пусто — мой профиль)", self.targetPeerId == self.context.account.peerId ? "" : self.targetTitle)]) { [weak self] values in
            guard let self, let input = values.first else { return }
            if input.isEmpty {
                self.targetPeerId = self.context.account.peerId; self.targetTitle = "Мой профиль"
                VisualGramLocalAppearance.shared.update(accountId: self.context.account.peerId) { _ in }
                return
            }
            let name = input.trimmingCharacters(in: CharacterSet(charactersIn: "@"))
            self.disposables.add((self.context.engine.peers.resolvePeerByName(name: name, referrer: nil) |> deliverOnMainQueue).start(next: { [weak self] result in
                guard let self, case let .result(peer) = result else { return }
                guard let peer, case .user = peer else { self.message("Пользователь не найден."); return }
                self.targetPeerId = peer.id; self.targetTitle = "@\(name)"
                VisualGramLocalAppearance.shared.update(accountId: self.context.account.peerId) { _ in }
            }))
        }
    }

    private func editPhone() {
        let item = self.appearance.phoneNumber
        self.form(title: "Визуальный номер профиля", fields: [("Номер: +7… или +888… (пусто — убрать)", item.map { "+\($0.name)" } ?? ""), ("Дата: yyyy-MM-dd HH:mm", self.dateFormatter.string(from: Date(timeIntervalSince1970: TimeInterval(item?.purchaseDate ?? Int32(Date().timeIntervalSince1970))))), ("Цена TON (для +888)", item.map { String(Double($0.tonAmount) / 1_000_000_000) } ?? "100"), ("Цена USD (для +888)", item.map { String(Double($0.usdAmount) / 100) } ?? "250")]) { [weak self] values in
            guard let self, values.count == 4 else { return }
            if values[0].isEmpty { self.update { $0.phoneNumber = nil }; return }
            let number = values[0].filter { $0.isNumber }
            guard number.range(of: "^[0-9]{5,15}$", options: .regularExpression) != nil, let date = self.dateFormatter.date(from: values[1]), date.timeIntervalSince1970 >= 0, date.timeIntervalSince1970 <= Double(Int32.max), let ton = self.minorAmount(values[2], scale: 1_000_000_000), let usd = self.minorAmount(values[3], scale: 100) else { self.message("Проверь номер, дату и цены."); return }
            self.update { $0.enabled = true; $0.phoneNumber = VisualGramUsername(name: number, purchaseDate: Int32(date.timeIntervalSince1970), tonAmount: ton, usdAmount: usd) }
        }
    }

    private func editRating() {
        let rating = self.appearance.starRating
        self.form(title: "Рейтинг Telegram", fields: [("Уровень (пусто — настоящий рейтинг)", rating.map { String($0.level) } ?? ""), ("Звёзды на начало уровня", rating.map { String($0.currentLevelStars) } ?? "0"), ("Текущие звёзды рейтинга", rating.map { String($0.stars) } ?? "0"), ("Звёзды следующего уровня (необязательно)", rating?.nextLevelStars.map(String.init) ?? "1000")]) { [weak self] values in
            guard let self, values.count == 4 else { return }
            if values[0].isEmpty { self.update { $0.starRating = nil }; return }
            guard let level = Int32(values[0]), (-1...1_000_000).contains(level), let current = Int64(values[1]), let stars = Int64(values[2]) else { self.message("Проверь уровень и числа звёзд."); return }
            let next = values[3].isEmpty ? nil : Int64(values[3])
            guard values[3].isEmpty || next != nil, current != Int64.min, stars != Int64.min, current <= stars, (level < 0 ? stars < 0 && (next.map { $0 <= 0 } ?? true) : current >= 0), next.map({ $0 > stars && $0 > current }) ?? true else { self.message("Начало уровня должно быть не выше текущих звёзд, а следующий порог — выше них. Для отрицательного рейтинга укажи уровень -1, отрицательные звёзды и следующий порог не выше 0."); return }
            self.update { $0.enabled = true; $0.starRating = TelegramStarRating(level: level, currentLevelStars: current, stars: stars, nextLevelStars: next) }
        }
    }

    private func configureVerification(forceSetup: Bool = false) {
        if !forceSetup, let template = VisualGramLocalAppearance.shared.appearance(accountId: self.context.account.peerId).majorTemplate {
            self.update { $0.enabled = true; $0.verification = template }
            return
        }
        self.form(title: "Значок Major", fields: [("Бот-верификатор или пользователь со значком", "major")]) { [weak self] values in
            guard let self, let input = values.first else { return }
            let name = input.trimmingCharacters(in: CharacterSet(charactersIn: "@"))
            if name.isEmpty { self.update { $0.verification = nil }; return }
            self.disposables.add((self.context.engine.peers.resolvePeerByName(name: name, referrer: nil)
            |> deliverOnMainQueue).start(next: { [weak self] result in
                guard let self, case let .result(peer) = result else { return }
                guard let peer else { self.message("Бот не найден."); return }
                self.disposables.add((self.context.engine.peers.fetchAndUpdateCachedPeerData(peerId: peer.id)
                |> mapToSignal { _ in self.context.engine.data.get(TelegramEngine.EngineData.Item.Peer.CachedData(id: peer.id)) }
                |> deliverOnMainQueue).start(next: { [weak self] cached in
                    guard let self else { return }
                    let template: PeerVerification
                    if let verification = (cached as? CachedUserData)?.verification { template = verification }
                    else if let settings = (cached as? CachedUserData)?.botInfo?.verifierSettings { template = PeerVerification(botId: peer.id, iconFileId: settings.iconFileId, description: settings.customDescription ?? settings.companyName) }
                    else { self.message("На этом профиле нет значка. Укажи @юзернейм человека с верификацией Major или её официального бота. После первого выбора значок включается одним переключателем."); return }
                    VisualGramLocalAppearance.shared.update(accountId: self.context.account.peerId) { $0.majorTemplate = template }
                    self.update { $0.enabled = true; $0.verification = template }
                }))
            }))
        }
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
        self.direction = direction
        self.form(title: direction == .sent ? "Кому отправить локально" : "Кто подарил подарок", fields: [(direction == .sent ? "Юзернейм получателя" : "Юзернейм отправителя (необязательно)", ""), ("Дата: yyyy-MM-dd HH:mm", self.dateFormatter.string(from: Date())), ("Подпись к подарку", "")]) { [weak self] values in
            guard let self, values.count == 3, let date = self.dateFormatter.date(from: values[1]), date.timeIntervalSince1970 >= 0, date.timeIntervalSince1970 <= Double(Int32.max) else { self?.message("Укажи корректную дату."); return }
            self.giftDate = Int32(date.timeIntervalSince1970)
            self.giftText = values[2]
            self.counterpartyId = nil
            if values[0].isEmpty {
                if direction == .sent { self.message("Укажи получателя для локальной карточки в чате.") }
                else { completion() }
                return
            }
            let name = values[0].trimmingCharacters(in: CharacterSet(charactersIn: "@"))
            self.disposables.add((self.context.engine.peers.resolvePeerByName(name: name, referrer: nil)
            |> deliverOnMainQueue).start(next: { [weak self] result in
                guard let self, case let .result(peer) = result else { return }
                guard let peer, case .user = peer else { self.message("Пользователь не найден."); return }
                self.counterpartyId = peer.id.toInt64()
                completion()
            }))
        }
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
        self.form(title: "Добавить NFT-подарок", fields: [("Ссылка t.me/nft/… или slug", "")]) { [weak self] values in
            guard let self, let input = values.first else { return }
            let slug = input.components(separatedBy: "?")[0].trimmingCharacters(in: CharacterSet(charactersIn: "/")).components(separatedBy: "/").last ?? ""
            guard slug.range(of: "^[A-Za-z0-9]+-[0-9]+$", options: .regularExpression) != nil else { self.message("Пример: PlushPepe-1 или ссылка на подарок."); return }
            self.disposables.add((self.context.engine.payments.getUniqueStarGift(slug: slug)
            |> deliverOnMainQueue).start(next: { [weak self] gift in self?.previewGift(.unique(gift)) }, error: { [weak self] _ in self?.message("Не удалось загрузить подарок. Проверь ссылку и подключение.") }))
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
        let title = deliveryDate == nil ? (local.direction == .sent ? "Отправить локально" : "Получить локально") : "Отложить локально"
        let preview = GiftViewScreen(context: self.context, subject: subject, customAction: .init(title: title, action: { [weak self] in
            guard let self else { return }
            if let deliveryDate {
                VisualGramLocalAppearance.shared.scheduleGift(accountId: self.context.account.peerId, targetPeerId: targetPeerId, gift: local, deliveryDate: deliveryDate)
            } else {
                self.deliverGift(local, targetPeerId: targetPeerId)
            }
        }))
        controller.push(preview)
    }

    private func deliverGift(_ gift: VisualGramGift, targetPeerId: EnginePeer.Id) {
        VisualGramLocalAppearance.shared.addGift(accountId: self.context.account.peerId, targetPeerId: targetPeerId, gift: gift)
        guard !UIAccessibility.isReduceMotionEnabled, let view = self.controller?.navigationController?.view ?? self.controller?.view, view.window != nil else { return }
        view.addSubview(ConfettiView(frame: view.bounds))
    }

    private func chooseGiftDelivery(_ gift: VisualGramGift, completion: @escaping (Int32?) -> Void) {
        let receiving = gift.direction == .received
        let alert = UIAlertController(title: receiving ? "Получить подарок" : "Отправить подарок", message: "Подарок будет виден только тебе в этом клиенте.", preferredStyle: .alert)
        alert.addAction(UIAlertAction(title: receiving ? "Получить сейчас" : "Отправить сейчас", style: .default, handler: { _ in completion(nil) }))
        alert.addAction(UIAlertAction(title: receiving ? "Отложить получение" : "Отложить отправку", style: .default, handler: { [weak self] _ in
            DispatchQueue.main.async { self?.pickDeliveryDate(currentTime: nil) { [weak self] time in
                guard let self else { return }
                completion(time)
            } }
        }))
        alert.addAction(UIAlertAction(title: "Отмена", style: .cancel))
        self.presentNative(alert)
    }

    private func pickDeliveryDate(currentTime: Int32?, completion: @escaping (Int32) -> Void) {
        guard let controller = self.controller else { return }
        let picker = ChatScheduleTimeController(context: self.context, mode: .scheduledMessages(sendWhenOnlineAvailable: false), style: .default, currentTime: currentTime, completion: { [weak self] time in
            guard time > Int32(clamping: Int64(Date().timeIntervalSince1970)), time < Int32.max - 1 else { self?.message("Выбери время в будущем."); return }
            completion(time)
        })
        controller.present(picker, in: .window(.root))
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

    private func openGift(index: Int) {
        guard self.appearance.gifts.indices.contains(index), self.controller != nil else { return }
        let local = self.appearance.gifts[index]
        let alert = UIAlertController(title: "Локальный подарок", message: nil, preferredStyle: .alert)
        if local.direction == .received && local.isHistoryOnly != true && self.targetPeerId == self.context.account.peerId {
            alert.addAction(UIAlertAction(title: (local.pinnedToTop ?? false) ? "Открепить" : "Закрепить", style: .default, handler: { [weak self] _ in
                guard let self else { return }
                if !(local.pinnedToTop ?? false), self.appearance.gifts.filter({ $0.pinnedToTop ?? false }).count >= 6 { self.message("Можно закрепить до 6 локальных подарков."); return }
                _ = VisualGramLocalAppearance.shared.updateGift(accountId: self.context.account.peerId, reference: local.reference(accountId: self.targetPeerId)) { $0.pinnedToTop = !($0.pinnedToTop ?? false); if $0.pinnedToTop == true { $0.savedToProfile = true } }
            }))
            alert.addAction(UIAlertAction(title: (local.savedToProfile ?? true) ? "Скрыть из профиля" : "Показать в профиле", style: .default, handler: { [weak self] _ in
                guard let self else { return }
                _ = VisualGramLocalAppearance.shared.updateGift(accountId: self.context.account.peerId, reference: local.reference(accountId: self.targetPeerId)) { $0.savedToProfile = !($0.savedToProfile ?? true); if $0.savedToProfile == false { $0.pinnedToTop = false } }
            }))
            alert.addAction(UIAlertAction(title: "Изменить дату и подпись", style: .default, handler: { [weak self] _ in
                guard let self else { return }
                self.form(title: "Данные локального подарка", fields: [("Дата: yyyy-MM-dd HH:mm", self.dateFormatter.string(from: Date(timeIntervalSince1970: TimeInterval(local.date)))), ("Подпись", local.text)]) { [weak self] values in
                    guard let self, values.count == 2, let date = self.dateFormatter.date(from: values[0]), date.timeIntervalSince1970 >= 0, date.timeIntervalSince1970 <= Double(Int32.max) else { self?.message("Проверь дату."); return }
                    _ = VisualGramLocalAppearance.shared.updateGift(accountId: self.context.account.peerId, reference: local.reference(accountId: self.targetPeerId)) { $0.date = Int32(date.timeIntervalSince1970); $0.text = values[1] }
                }
            }))
        }
        alert.addAction(UIAlertAction(title: "Открыть подарок", style: .default, handler: { [weak self] _ in
            guard let self else { return }
            let show: (EnginePeer?) -> Void = { [weak self] sender in
                guard let self else { return }
                let screen: GiftViewScreen
                if local.direction == .sent {
                    let subject: GiftViewScreen.Subject
                    switch local.displayGift(accountId: self.targetPeerId) {
                    case let .unique(gift): subject = .uniqueGift(gift, nil)
                    case let .generic(gift): subject = .soldOutGift(gift)
                    }
                    screen = GiftViewScreen(context: self.context, subject: subject, customAction: .init(title: "Удалить локально", action: { [weak self] in self?.update { $0.gifts.removeAll { $0.identifier == local.identifier } } }))
                } else {
                    screen = GiftViewScreen(context: self.context, subject: .profileGift(self.targetPeerId, local.profileGift(accountId: self.targetPeerId, sender: sender)))
                }
                self.controller?.push(screen)
            }
            if let senderId = local.counterpartyId {
                self.disposables.add((self.context.engine.data.get(TelegramEngine.EngineData.Item.Peer.Peer(id: EnginePeer.Id(senderId))) |> deliverOnMainQueue).start(next: show))
            } else { show(nil) }
        }))
        if local.direction == .received, case let .unique(gift) = local.displayGift(accountId: self.targetPeerId) {
            alert.addAction(UIAlertAction(title: "Поставить в статус", style: .default, handler: { [weak self] _ in
                guard let self else { return }
                self.update { $0.enabled = true; $0.premium = true }
                _ = VisualGramLocalAppearance.shared.setLocalGiftStatus(accountId: self.context.account.peerId, targetPeerId: self.targetPeerId, gift: gift, expirationDate: nil)
            }))
        }
        alert.addAction(UIAlertAction(title: "Удалить локально", style: .destructive, handler: { [weak self] _ in self?.update { $0.gifts.removeAll { $0.identifier == local.identifier } } }))
        alert.addAction(UIAlertAction(title: "Отмена", style: .cancel))
        self.presentNative(alert)
    }
}

func visualGramAppearanceController(context: AccountContext) -> ViewController {
    let actions = VisualGramAppearanceActions(context: context)
    let signal = combineLatest(context.sharedContext.presentationData, VisualGramLocalAppearance.shared.changes, actions.expandedLists.get())
    |> deliverOnMainQueue
    |> map { presentationData, _, expanded -> (ItemListControllerState, (ItemListNodeState, Any)) in
        let value = actions.appearance
        var entries: [VisualGramAppearanceEntry] = []
        func add(_ id: Int32, _ section: Int32, _ title: String, _ kind: VisualGramAppearanceEntry.Kind) {
            entries.append(VisualGramAppearanceEntry(stableId: id, section: section, title: title, kind: kind, theme: presentationData.theme))
        }
        add(0, 0, "Локальное оформление", .toggle(value.enabled))
        add(1, 0, "Визуальный Premium", .toggle(value.premium))
        add(2, 0, "Галочка Telegram", .toggle(value.verified))
        add(3, 0, "Верификация Major", .toggle(value.verification != nil))
        add(4, 0, "Эмодзи-статус", .button(""))
        add(5, 0, "Убрать локальный статус", .button(""))
        add(6, 0, "Оформление видно только тебе. Оплата и реальные действия используют данные Telegram.", .info)
        add(7, 0, "Чей профиль оформить", .button(actions.targetTitle))
        add(8, 0, "Выбрать исходный значок Major", .button(""))
        add(9, 0, "Сборка Telegram: \(Bundle.main.object(forInfoDictionaryKey: "CFBundleVersion") as? String ?? "—")", .info)
        add(10, 1, "Добавить NFT-юзернейм", .button(""))
        add(11, 1, "Номер профиля / +888", .button(value.phoneNumber.map { "+\($0.name)" } ?? "Настоящий номер"))
        add(12, 1, "Рейтинг Telegram", .button(value.starRating.map { "Уровень \($0.level)" } ?? "Настоящий рейтинг"))
        add(13, 1, "Юзернеймы (\(value.usernames.count))", .button(expanded & 1 == 0 ? "Развернуть" : "Свернуть"))
        add(20, 2, "Получить обычный подарок локально", .button(""))
        add(21, 2, "Получить NFT-подарок локально", .button(""))
        add(22, 2, "Отправить обычный подарок локально", .button(""))
        add(23, 2, "Отправить NFT-подарок локально", .button(""))
        add(24, 2, "Добавить NFT в профиль", .button(""))
        add(30, 3, "Визуальные звёзды", .button(value.stars.map(String.init) ?? "Настоящий баланс"))
        add(40, 4, "Сбросить локальное оформление", .button(""))
        add(25, 2, "Отложенные подарки появятся в выбранное время при открытом клиенте или при следующем открытии. Отправка остаётся локальной.", .info)
        add(26, 2, "Подарки (\(value.gifts.count))", .button(expanded & 2 == 0 ? "Развернуть" : "Свернуть"))
        if expanded & 1 != 0 {
        for (index, username) in value.usernames.enumerated() { add(1000 + Int32(index), 1, "@\(username.name)", .button("\(Double(username.tonAmount) / 1_000_000_000) TON")) }
        }
        if expanded & 2 != 0 {
        for (index, local) in value.gifts.enumerated() {
            let title: String
            switch local.gift {
            case let .unique(gift): title = "\(gift.title) #\(gift.number)"
            case let .generic(gift): title = gift.title ?? "Подарок \(gift.id)"
            }
            add(2000 + Int32(index), 2, local.direction == .sent ? "Отправлено: \(title)" : title, .button(""))
        }
        }
        let queue = VisualGramLocalAppearance.shared.pendingScheduledGifts.filter { $0.targetPeerId == actions.targetPeerId.toInt64() }.sorted { $0.deliveryDate < $1.deliveryDate }
        let formatter = DateFormatter()
        formatter.dateStyle = .short
        formatter.timeStyle = .short
        for (index, pending) in queue.prefix(1000).enumerated() {
            let title: String
            switch pending.gift.gift {
            case let .unique(gift): title = "\(gift.title) #\(gift.number)"
            case let .generic(gift): title = gift.title ?? "Подарок \(gift.id)"
            }
            add(3000 + Int32(index), 5, "Отложено: \(title)", .button(formatter.string(from: Date(timeIntervalSince1970: TimeInterval(pending.deliveryDate)))))
        }
        entries.sort()
        let controllerState = ItemListControllerState(presentationData: ItemListPresentationData(presentationData), title: .text("VisualGram"), leftNavigationButton: nil, rightNavigationButton: nil, backNavigationButton: ItemListBackButton(title: presentationData.strings.Common_Back))
        let listState = ItemListNodeState(presentationData: ItemListPresentationData(presentationData), entries: entries, style: .blocks, animateChanges: false)
        return (controllerState, (listState, actions))
    }
    let controller = ItemListController(context: context, state: signal)
    actions.controller = controller
    return controller
}
