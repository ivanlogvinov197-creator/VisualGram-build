import Foundation
import UIKit
import Display
import AccountContext
import TelegramCore
import SwiftSignalKit
import ConfettiEffect

// One completion path for local purchases and transfers. The attachment owner
// closes its sheet; the navigation stack changes at most once.
public func visualGramFinishGift(context: AccountContext, peerId: EnginePeer.Id, controller: ViewController, completion: (() -> Void)? = nil) {
    let navigationController = (controller.navigationController as? NavigationController)
        ?? (context.sharedContext.mainWindow?.viewController as? NavigationController)
    let wasInStack = navigationController?.viewControllers.contains(where: { $0 === controller }) == true
    let source = controller as? VisualGramGiftFlowController
    let inherited = navigationController?.viewControllers.reversed().compactMap { ($0 as? VisualGramGiftFlowController)?.visualGramGiftCompletion }.first
    let closeAttachment = source?.visualGramGiftCompletion ?? inherited ?? completion
    closeAttachment?()

    if let navigationController {
        var controllers = navigationController.viewControllers.filter {
            !($0 is VisualGramGiftFlowController) && !($0 is GiftOptionsScreenProtocol) && !($0 is GiftSetupScreenProtocol)
                && !($0 is ContactSelectionController) && !($0 is PeerInfoScreen)
        }
        if let index = controllers.lastIndex(where: {
            guard let chat = $0 as? ChatController else { return false }
            if case let .peer(id) = chat.chatLocation { return id == peerId }
            return false
        }), let chat = controllers[index] as? ChatController {
            chat.hintPlayNextOutgoingGift()
            controllers = Array(controllers.prefix(index + 1))
        } else if peerId.namespace == Namespaces.Peer.CloudUser {
            let chat = context.sharedContext.makeChatController(context: context, chatLocation: .peer(id: peerId), subject: nil, botStart: nil, mode: .standard(.default), params: nil)
            chat.hintPlayNextOutgoingGift()
            controllers.append(chat)
        }
        let previous = navigationController.viewControllers
        if previous.count != controllers.count || zip(previous, controllers).contains(where: { pair in pair.0 !== pair.1 }) {
            navigationController.setViewControllers(controllers, animated: true)
        }
    }
    if let giftController = controller as? GiftViewScreen, !wasInStack {
        // A presented preview is outside the navigation stack.
        giftController.dismissAnimated()
    }
    Queue.mainQueue().after(0.35) { [weak navigationController] in
        guard !UIAccessibility.isReduceMotionEnabled else { return }
        let navigationView = navigationController?.view
        let view = navigationView?.window != nil ? navigationView : context.sharedContext.mainWindow?.viewController?.view
        if let view, view.window != nil { view.addSubview(ConfettiView(frame: view.bounds)) }
    }
}
