import Foundation
import UIKit
import Display
import AccountContext
import ConfettiEffect
import SwiftSignalKit
import TelegramCore

/// Foreground-only local delivery. No outbox, Bot API, or account mutation RPC.
final class VisualGramGiftDelivery {
    private weak var context: AccountContext?
    private let accountId: EnginePeer.Id
    private let subscriptions = DisposableSet()
    private var observers: [NSObjectProtocol] = []
    private var timer: Foundation.Timer?
    private var isPrimary = false

    init(context: AccountContext) {
        self.context = context
        self.accountId = context.account.peerId
        let recordId = context.account.id
        self.subscriptions.add((context.sharedContext.activeAccountsWithInfo |> deliverOnMainQueue).start(next: { [weak self] primary, _ in
            self?.isPrimary = primary == recordId
            self?.refresh()
        }))
        self.subscriptions.add((VisualGramLocalAppearance.shared.changes |> deliverOnMainQueue).start(next: { [weak self] _ in self?.refresh() }))
        for name in [UIApplication.didBecomeActiveNotification, UIApplication.didEnterBackgroundNotification, UIApplication.significantTimeChangeNotification] {
            self.observers.append(NotificationCenter.default.addObserver(forName: name, object: nil, queue: .main) { [weak self] _ in self?.refresh() })
        }
    }

    deinit { self.stop() }

    func stop() {
        self.timer?.invalidate(); self.timer = nil
        self.subscriptions.dispose()
        for observer in self.observers { NotificationCenter.default.removeObserver(observer) }
        self.observers.removeAll()
    }

    private func refresh() {
        self.timer?.invalidate(); self.timer = nil
        guard self.isPrimary, UIApplication.shared.applicationState == .active else { return }
        let store = VisualGramLocalAppearance.shared
        guard !store.pendingScheduledGifts.isEmpty else { return }
        // Wait for the main window on a cold launch, so due gifts have a visible animation.
        guard let controller = self.context?.sharedContext.mainWindow?.viewController, controller.isViewLoaded, controller.view.window != nil, controller.view.bounds.width > 0.0 else {
            self.armTimer(after: 0.25)
            return
        }
        let now = Int32(clamping: Int64(Date().timeIntervalSince1970))
        let delivered = store.deliverAllScheduledGifts(now: now)
        if delivered.contains(where: { store.appearance(accountId: self.accountId, targetPeerId: EnginePeer.Id($0.targetPeerId)).enabled }), !UIAccessibility.isReduceMotionEnabled {
            controller.view.addSubview(ConfettiView(frame: controller.view.bounds))
        }
        guard let next = store.pendingScheduledGifts.map({ $0.deliveryDate }).min() else { return }
        let delay = max(0.1, min(3600.0, Double(next) - Date().timeIntervalSince1970))
        self.armTimer(after: delay)
    }

    private func armTimer(after delay: TimeInterval) {
        let timer = Foundation.Timer(timeInterval: delay, repeats: false) { [weak self] _ in self?.refresh() }
        self.timer = timer
        RunLoop.main.add(timer, forMode: .common)
    }
}
