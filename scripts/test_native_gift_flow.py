"""Exercise the production completion helper with a lightweight navigation stack."""
from pathlib import Path
import subprocess
import tempfile


def source():
    root = Path(__file__).resolve().parents[1]
    helper = (root / 'native/VisualGramGiftFlow.swift').read_text(encoding='utf-8')
    helper = '\n'.join(line for line in helper.splitlines() if not line.startswith('import '))
    return STUBS + helper + CHECKS


STUBS = r'''
import Foundation
public enum Namespaces { public enum Peer { public static let CloudUser: Int32 = 0 } }
public enum EnginePeer { public struct Id: Equatable { public let value: Int64; public var namespace: Int32 { 0 }; public init(_ value: Int64) { self.value = value } } }
public enum ChatLocation { case peer(id: EnginePeer.Id) }
public enum ChatMode { public enum Standard { case `default` }; case standard(Standard) }
public class View {
    public var window: Int? = 1
    public let bounds = CGRect.zero
    public var confettiCount = 0
    public func addSubview(_ view: ConfettiView) { confettiCount += 1 }
}
public final class ConfettiView { public init(frame: CGRect) {} }
public enum UIAccessibility { public static var isReduceMotionEnabled = false }
public final class Queue { public static func mainQueue() -> Queue { Queue() }; public func after(_ delay: Double, _ action: () -> Void) { action() } }
public class ViewController {
    public var view = View()
    public weak var navigationController: NavigationController?
    public var presentingViewController: ViewController?
}
public protocol ChatController: ViewController { var chatLocation: ChatLocation { get }; func hintPlayNextOutgoingGift() }
public protocol GiftOptionsScreenProtocol {}
public protocol GiftSetupScreenProtocol {}
public protocol ContactSelectionController {}
public protocol PeerInfoScreen {}
public protocol VisualGramGiftFlowController: AnyObject { var visualGramGiftCompletion: (() -> Void)? { get set } }
public final class GiftViewScreen: ViewController, VisualGramGiftFlowController {
    public var visualGramGiftCompletion: (() -> Void)?
    public var dismissCount = 0
    public func dismissAnimated() { dismissCount += 1; presentingViewController = nil }
}
public final class GiftMarket: ViewController, VisualGramGiftFlowController { public var visualGramGiftCompletion: (() -> Void)? }
public final class GiftOptions: ViewController, GiftOptionsScreenProtocol, VisualGramGiftFlowController { public var visualGramGiftCompletion: (() -> Void)? }
public final class GiftSetup: ViewController, GiftSetupScreenProtocol {}
public final class Picker: ViewController, ContactSelectionController {}
public final class Profile: ViewController, PeerInfoScreen {}
public final class Chat: ViewController, ChatController {
    public let chatLocation: ChatLocation
    public var hints = 0
    public init(_ id: EnginePeer.Id) { self.chatLocation = .peer(id: id) }
    public func hintPlayNextOutgoingGift() { hints += 1 }
}
public final class NavigationController: ViewController {
    public var viewControllers: [ViewController] = []
    public var transitions = 0
    public func install(_ controllers: [ViewController]) { viewControllers = controllers; controllers.forEach { $0.navigationController = self } }
    public func setViewControllers(_ controllers: [ViewController], animated: Bool) { assert(animated); transitions += 1; install(controllers) }
}
public final class Window { public var viewController: ViewController? }
public final class SharedContext {
    public var mainWindow: Window? = Window()
    public var created = 0
    public func makeChatController(context: AccountContext, chatLocation: ChatLocation, subject: Int?, botStart: Int?, mode: ChatMode, params: Int?) -> Chat {
        created += 1
        switch chatLocation { case let .peer(id): return Chat(id) }
    }
}
public final class AccountContext { public let sharedContext = SharedContext() }
'''


CHECKS = r'''
let peer = EnginePeer.Id(20)
let context = AccountContext()
let navigation = NavigationController()
context.sharedContext.mainWindow?.viewController = navigation
let root = ViewController(), chat = Chat(peer), options = GiftOptions(), market = GiftMarket(), preview = GiftViewScreen(), picker = Picker()
var closed = 0
options.visualGramGiftCompletion = { closed += 1 }
navigation.install([root, chat, options, market, preview, picker])
visualGramFinishGift(context: context, peerId: peer, controller: picker)
assert(navigation.viewControllers.count == 2 && navigation.viewControllers.last === chat)
assert(navigation.transitions == 1 && context.sharedContext.created == 0)
assert(chat.hints == 1 && closed == 1 && navigation.view.confettiCount == 1)
assert(preview.dismissCount == 0, "pushed preview triggered a second dismissal")
// Paperclip completion only closes its attachment, without re-opening an existing chat.
navigation.install([root, chat])
visualGramFinishGift(context: context, peerId: peer, controller: chat, completion: { closed += 1 })
assert(navigation.transitions == 1 && closed == 2 && navigation.view.confettiCount == 2)
// A purchase for another user creates one chat and removes both market and preview.
let recipient = EnginePeer.Id(30)
navigation.install([root, chat, Profile(), market, preview])
visualGramFinishGift(context: context, peerId: recipient, controller: preview)
assert(navigation.viewControllers.count == 3 && context.sharedContext.created == 1 && navigation.transitions == 2)
assert(navigation.viewControllers.last is Chat && navigation.view.confettiCount == 3)
// Presented previews close once. Detached sheet views use the visible main window.
let detachedNavigation = NavigationController(), modal = GiftViewScreen()
detachedNavigation.view.window = nil
detachedNavigation.install([root])
modal.navigationController = detachedNavigation
modal.presentingViewController = root
visualGramFinishGift(context: context, peerId: recipient, controller: modal)
assert(modal.dismissCount == 1 && navigation.view.confettiCount == 4 && detachedNavigation.view.confettiCount == 0)
UIAccessibility.isReduceMotionEnabled = true
let before = navigation.view.confettiCount
visualGramFinishGift(context: context, peerId: recipient, controller: navigation.viewControllers.last!)
assert(navigation.view.confettiCount == before)
print("PASS: one navigation transition, one attachment completion, one confetti, existing/new chat, pushed/modal preview, detached sheet and reduced motion")
'''


if __name__ == '__main__':
    with tempfile.TemporaryDirectory(prefix='visualgram-flow-') as folder:
        swift, executable = Path(folder) / 'GiftFlowTests.swift', Path(folder) / 'gift-flow-tests'
        swift.write_text(source(), encoding='utf-8')
        subprocess.run(['xcrun', 'swiftc', str(swift), '-o', str(executable)], check=True)
        subprocess.run([str(executable)], check=True)
