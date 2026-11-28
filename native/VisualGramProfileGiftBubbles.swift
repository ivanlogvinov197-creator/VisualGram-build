import Foundation
import UIKit
import AccountContext
import Display
import GlassBackgroundComponent
import EmojiTextAttachmentView
import AnimationCache
import MultiAnimationRenderer
import SwiftSignalKit
import TelegramCore
import TelegramPresentationData

final class VisualGramProfileGiftBubbles: UIView, UIGestureRecognizerDelegate {
    private struct Layout {
        let avatar: CGRect
        let travel: CGRect
        let orbitCenter: CGPoint
        let orbitRadius: CGSize
        let diameter: CGFloat
        let visibility: CGFloat

        init?(component: PeerInfoGiftsCoverComponent, size: CGSize) {
            let diameter = min(52.0, max(38.0, component.avatarSize.width * 0.46))
            let radius = diameter * 0.5
            let avatar = CGRect(origin: CGPoint(
                x: component.avatarCenter.x - component.avatarSize.width * 0.5,
                y: component.avatarCenter.y - component.avatarSize.height * 0.5
            ), size: component.avatarSize)
            let top = component.statusBarHeight + radius + 2.0
            let bottom = size.height - radius - 4.0
            let side = radius + 7.0
            let horizontalSpace = min(avatar.midX - side, size.width - side - avatar.midX)
            let visibility = max(0.0, 1.0 - component.avatarTransitionFraction * 1.8)
            guard avatar.width > 30.0, horizontalSpace > radius, bottom - top > 14.0, visibility > 0.03 else {
                return nil
            }
            let orbitTop = max(top, avatar.midY - avatar.height * 0.47)
            let orbitBottom = min(bottom, avatar.midY + avatar.height * 0.36)
            guard orbitBottom > orbitTop else {
                return nil
            }
            self.avatar = avatar
            self.travel = CGRect(x: side, y: top, width: size.width - 2.0 * side, height: bottom - top)
            self.orbitCenter = CGPoint(x: avatar.midX, y: (orbitBottom + orbitTop) * 0.5)
            self.orbitRadius = CGSize(
                width: min(horizontalSpace, avatar.width * 1.13 + radius),
                height: (orbitBottom - orbitTop) * 0.5
            )
            self.diameter = diameter
            self.visibility = visibility
        }

        func constrain(_ point: CGPoint) -> CGPoint {
            return CGPoint(
                x: min(max(point.x, self.travel.minX), self.travel.maxX),
                y: min(max(point.y, self.travel.minY), self.travel.maxY)
            )
        }
    }

    private var bubbles: [VisualGramProfileGiftBubble] = []
    private let avatarShell = CAGradientLayer()
    var accessibleGifts: [UIView] { self.bubbles.filter { $0.isAccessibilityElement } }
    private var layout: Layout?
    private var flight: SharedDisplayLinkDriver.Link?
    private var phase: CGFloat = -.pi * 0.30
    private var reduceMotion = UIAccessibility.isReduceMotionEnabled
    private var openGift: ((ProfileGiftsContext.State.StarGift) -> Void)?
    private weak var pendingDragBubble: VisualGramProfileGiftBubble?
    private weak var pendingTapBubble: VisualGramProfileGiftBubble?
    private var draggedBubble: VisualGramProfileGiftBubble?
    private var dragPosition = CGPoint.zero
    private var grabOffset = CGPoint.zero
    private lazy var pan = UIPanGestureRecognizer(target: self, action: #selector(self.moveBubble(_:)))
    private lazy var tap = UITapGestureRecognizer(target: self, action: #selector(self.tapBubble(_:)))

    override init(frame: CGRect) {
        super.init(frame: frame)
        self.clipsToBounds = true
        self.avatarShell.type = .radial
        self.avatarShell.startPoint = CGPoint(x: 0.51, y: 0.50)
        self.avatarShell.endPoint = CGPoint(x: 1.01, y: 0.50)
        self.avatarShell.colors = [UIColor.clear.cgColor, UIColor.clear.cgColor, UIColor.white.withAlphaComponent(0.18).cgColor, UIColor.white.withAlphaComponent(0.34).cgColor]
        self.avatarShell.locations = [0, 0.85, 0.97, 1]
        self.layer.addSublayer(self.avatarShell)
        self.pan.maximumNumberOfTouches = 1
        self.pan.delegate = self
        self.tap.delegate = self
        self.tap.require(toFail: self.pan)
        self.addGestureRecognizer(self.pan)
        self.addGestureRecognizer(self.tap)
        NotificationCenter.default.addObserver(self, selector: #selector(self.motionPreferenceChanged(_:)), name: UIAccessibility.reduceMotionStatusDidChangeNotification, object: nil)
    }

    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    deinit {
        self.flight?.invalidate()
        NotificationCenter.default.removeObserver(self)
    }

    override func didMoveToWindow() {
        super.didMoveToWindow()
        if self.window == nil {
            self.finishDrag(velocity: .zero)
        }
        self.updateDisplayLink()
    }

    func update(component: PeerInfoGiftsCoverComponent, gifts: [ProfileGiftsContext.State.StarGift]) {
        self.openGift = component.action
        self.layout = Layout(component: component, size: self.bounds.size)
        let isDark = component.context.sharedContext.currentPresentationData.with { $0 }.theme.overallDarkAppearance
        let existing = Dictionary(uniqueKeysWithValues: self.bubbles.map { ($0.slug, $0) })
        var seen = Set<String>()
        var updated: [VisualGramProfileGiftBubble] = []
        for gift in gifts.prefix(12) {
            guard case let .unique(uniqueGift) = gift.gift, seen.insert(uniqueGift.slug).inserted else {
                continue
            }
            let bubble: VisualGramProfileGiftBubble
            if let current = existing[uniqueGift.slug] {
                bubble = current
                bubble.gift = gift
            } else {
                bubble = VisualGramProfileGiftBubble(context: component.context, gift: gift, uniqueGift: uniqueGift)
                bubble.open = { [weak self] gift in self?.openGift?(gift) }
                self.addSubview(bubble)
            }
            if let layout = self.layout {
                bubble.updateGlass(diameter: layout.diameter, isDark: isDark)
            }
            updated.append(bubble)
        }
        for bubble in self.bubbles where !seen.contains(bubble.slug) {
            if self.draggedBubble === bubble {
                self.finishDrag(velocity: .zero)
            }
            bubble.removeFromSuperview()
        }
        self.bubbles = updated
        self.isHidden = self.layout == nil
        if let layout = self.layout {
            self.avatarShell.frame = layout.avatar
            self.avatarShell.cornerRadius = layout.avatar.width * 0.5
            self.avatarShell.opacity = Float(layout.visibility)
        }
        if self.isHidden {
            self.finishDrag(velocity: .zero)
        }
        self.placeBubbles(delta: 0.0)
        self.updateDisplayLink()
    }

    @objc private func motionPreferenceChanged(_ notification: Notification) {
        self.reduceMotion = UIAccessibility.isReduceMotionEnabled
        for bubble in self.bubbles where bubble !== self.draggedBubble {
            bubble.offset = .zero
            bubble.velocity = .zero
            bubble.angularVelocity = 0
            bubble.resetPatternMotion()
        }
        self.placeBubbles(delta: 0.0)
        self.updateDisplayLink()
    }

    private func updateDisplayLink() {
        if self.window != nil && !self.isHidden && !self.bubbles.isEmpty && !self.reduceMotion {
            if self.flight == nil {
                self.flight = SharedDisplayLinkDriver.shared.add(framesPerSecond: .fps(60)) { [weak self] delta in
                    self?.placeBubbles(delta: min(max(delta, 0.0), 1.0 / 30.0))
                }
            }
        } else {
            self.flight?.invalidate()
            self.flight = nil
        }
    }

    private func placeBubbles(delta: CGFloat) {
        guard let layout = self.layout, !self.bubbles.isEmpty else {
            return
        }
        self.phase = (self.phase + delta * 0.48).truncatingRemainder(dividingBy: 2.0 * .pi)
        CATransaction.begin()
        CATransaction.setDisableActions(true)
        defer { CATransaction.commit() }

        for (index, bubble) in self.bubbles.enumerated() {
            bubble.phaseOffset = (bubble.phaseOffset + bubble.angularVelocity * delta).truncatingRemainder(dividingBy: 2.0 * .pi)
            bubble.angularVelocity *= exp(-0.48 * delta)
            let angle = self.phase + bubble.phaseOffset + 2.0 * .pi * CGFloat(index) / CGFloat(self.bubbles.count)
            let depth = sin(angle)
            let anchor = CGPoint(
                x: layout.orbitCenter.x + cos(angle) * layout.orbitRadius.width,
                y: layout.orbitCenter.y + depth * layout.orbitRadius.height
            )
            let dragging = self.draggedBubble === bubble
            if dragging {
                let position = layout.constrain(self.dragPosition)
                bubble.offset = CGPoint(x: position.x - anchor.x, y: position.y - anchor.y)
            } else if delta > 0.0 {
                let damping = exp(-7.0 * delta)
                bubble.velocity.x = (bubble.velocity.x - 34.0 * bubble.offset.x * delta) * damping
                bubble.velocity.y = (bubble.velocity.y - 34.0 * bubble.offset.y * delta) * damping
                bubble.offset.x += bubble.velocity.x * delta
                bubble.offset.y += bubble.velocity.y * delta
            }
            let proposed = CGPoint(x: anchor.x + bubble.offset.x, y: anchor.y + bubble.offset.y)
            let position = layout.constrain(proposed)
            if !dragging && delta > 0.0 {
                if position.x != proposed.x {
                    bubble.offset.x = position.x - anchor.x
                    bubble.velocity.x *= -0.32
                }
                if position.y != proposed.y {
                    bubble.offset.y = position.y - anchor.y
                    bubble.velocity.y *= -0.32
                }
            }
            let desiredScale = dragging ? min(2.3, max(1.25, 1.2 + hypot(bubble.offset.x, bubble.offset.y) / 130.0)) : 0.98 + depth * 0.22
            if self.reduceMotion || !bubble.hasBeenPlaced {
                bubble.depthScale = desiredScale
            } else {
                bubble.depthScale += (desiredScale - bubble.depthScale) * (1.0 - exp(-13.0 * delta))
            }
            let scale = bubble.depthScale * (0.65 + layout.visibility * 0.35)
            let rear = depth < 0.0 && !self.reduceMotion && !dragging && hypot(bubble.offset.x, bubble.offset.y) < 10.0
            let distance = hypot(position.x - layout.avatar.midX, position.y - layout.avatar.midY)
            let edge = layout.avatar.width * 0.5 + layout.diameter * scale * 0.5
            let visiblePart = rear ? min(1.0, max(0.0, (distance - edge + 16.0) / 16.0)) : 1.0
            bubble.center = position
            bubble.updatePatternMotion(position: position, delta: delta)
            bubble.hasBeenPlaced = true
            bubble.transform = CGAffineTransform(scaleX: scale, y: scale)
            bubble.layer.zPosition = dragging ? 2.0 : depth
            bubble.alpha = layout.visibility * visiblePart
            bubble.isAccessibilityElement = bubble.alpha >= 0.3
        }
    }

    private func bubble(at point: CGPoint) -> VisualGramProfileGiftBubble? {
        return self.bubbles.filter { bubble in
            let local = bubble.convert(point, from: self)
            let radius = bubble.bounds.width * 0.5
            return bubble.alpha >= 0.3 && hypot(local.x - radius, local.y - radius) <= radius
        }.max { $0.layer.zPosition < $1.layer.zPosition }
    }

    override func point(inside point: CGPoint, with event: UIEvent?) -> Bool {
        return !self.isHidden && self.bounds.contains(point) && self.bubble(at: point) != nil
    }

    func gestureRecognizer(_ gestureRecognizer: UIGestureRecognizer, shouldReceive touch: UITouch) -> Bool {
        let bubble = self.bubble(at: touch.location(in: self))
        if gestureRecognizer === self.pan {
            self.pendingDragBubble = bubble
        } else {
            self.pendingTapBubble = bubble
        }
        return bubble != nil
    }

    func gestureRecognizer(_ gestureRecognizer: UIGestureRecognizer, shouldBeRequiredToFailBy otherGestureRecognizer: UIGestureRecognizer) -> Bool {
        guard gestureRecognizer === self.pan, let scrollView = otherGestureRecognizer.view as? UIScrollView else { return false }
        return otherGestureRecognizer === scrollView.panGestureRecognizer && self.isDescendant(of: scrollView)
    }

    @objc private func tapBubble(_ gesture: UITapGestureRecognizer) {
        defer { self.pendingTapBubble = nil }
        if let bubble = self.pendingTapBubble, bubble.superview === self, !self.isHidden {
            self.openGift?(bubble.gift)
        }
    }

    @objc private func moveBubble(_ gesture: UIPanGestureRecognizer) {
        let point = gesture.location(in: self)
        switch gesture.state {
        case .began:
            guard let bubble = self.pendingDragBubble, bubble.superview === self else { return }
            self.draggedBubble = bubble
            let translation = gesture.translation(in: self)
            self.grabOffset = CGPoint(x: bubble.center.x - point.x + translation.x, y: bubble.center.y - point.y + translation.y)
            self.dragPosition = CGPoint(x: point.x + self.grabOffset.x, y: point.y + self.grabOffset.y)
        case .changed:
            self.dragPosition = CGPoint(x: point.x + self.grabOffset.x, y: point.y + self.grabOffset.y)
        case .ended:
            self.dragPosition = CGPoint(x: point.x + self.grabOffset.x, y: point.y + self.grabOffset.y)
            self.placeBubbles(delta: 0.0)
            self.finishDrag(velocity: gesture.velocity(in: self))
        case .cancelled, .failed:
            self.finishDrag(velocity: .zero)
        default:
            return
        }
        self.placeBubbles(delta: 0.0)
    }

    private func finishDrag(velocity: CGPoint) {
        if let bubble = self.draggedBubble {
            let speed = hypot(velocity.x, velocity.y)
            let limit = min(1.0, 1400.0 / max(speed, 1.0))
            bubble.velocity = self.reduceMotion ? .zero : CGPoint(x: velocity.x * limit, y: velocity.y * limit)
            if !self.reduceMotion, let layout = self.layout, let index = self.bubbles.firstIndex(where: { $0 === bubble }) {
                let baseAngle = self.phase + 2.0 * .pi * CGFloat(index) / CGFloat(self.bubbles.count)
                let release = VisualGramOrbitRelease(position: bubble.center, velocity: bubble.velocity, center: layout.orbitCenter, radii: layout.orbitRadius, baseAngle: baseAngle, previousAngle: baseAngle + bubble.phaseOffset)
                bubble.phaseOffset = release.phaseOffset
                bubble.offset = release.offset
                bubble.angularVelocity = release.angularVelocity
                bubble.velocity = release.residualVelocity
            }
            if self.reduceMotion {
                bubble.offset = .zero
            }
        }
        self.draggedBubble = nil
        self.pendingDragBubble = nil
    }
}

private final class VisualGramProfileGiftBubble: UIView {
    let slug: String
    var gift: ProfileGiftsContext.State.StarGift
    var offset = CGPoint.zero
    var velocity = CGPoint.zero
    var phaseOffset: CGFloat = 0
    var angularVelocity: CGFloat = 0
    var depthScale: CGFloat = 1
    var hasBeenPlaced = false
    private var lastPosition: CGPoint?
    private var lastVelocity = CGPoint.zero
    private var patternLayers: [CALayer] = []
    private var slosh = VisualGramPatternMotion()
    private var patternImage: PatternContentsTarget?
    private var patternLoad: Disposable?
    var open: ((ProfileGiftsContext.State.StarGift) -> Void)?
    private let glass = GlassBackgroundView(frame: .zero)
    private let highlight = CAGradientLayer()
    private let rim = CAShapeLayer()
    private let icon: CALayer
    private let tint: UIColor
    private var dark: Bool?

    init(context: AccountContext, gift: ProfileGiftsContext.State.StarGift, uniqueGift: StarGift.UniqueGift) {
        self.slug = uniqueGift.slug
        self.gift = gift
        self.icon = makeVisualGramGiftIconLayer(context: context, gift: gift, size: CGSize(width: 32.0, height: 32.0))
        var tint = UIColor.systemTeal
        for attribute in uniqueGift.attributes {
            if case let .backdrop(_, _, color, _, _, _, _) = attribute {
                tint = UIColor(rgb: UInt32(bitPattern: color))
                break
            }
        }
        self.tint = tint
        super.init(frame: .zero)

        self.isAccessibilityElement = true
        self.accessibilityLabel = "\(uniqueGift.title) #\(uniqueGift.number)"
        self.accessibilityTraits = .button
        self.glass.isUserInteractionEnabled = false
        self.addSubview(self.glass)
        self.highlight.startPoint = CGPoint(x: 0.18, y: 0.03)
        self.highlight.endPoint = CGPoint(x: 0.90, y: 0.95)
        self.highlight.colors = [UIColor.white.withAlphaComponent(0.36).cgColor, tint.withAlphaComponent(0.06).cgColor, tint.withAlphaComponent(0.22).cgColor]
        self.highlight.locations = [0.0, 0.48, 1.0]
        self.layer.addSublayer(self.highlight)
        self.rim.fillColor = UIColor.clear.cgColor
        self.rim.strokeColor = UIColor.white.withAlphaComponent(0.52).cgColor
        self.rim.lineWidth = 1.0
        self.layer.addSublayer(self.rim)
        self.layer.addSublayer(self.icon)
        self.layer.masksToBounds = true
        for attribute in uniqueGift.attributes {
            if case let .pattern(_, file, _) = attribute {
                self.loadPattern(file, context: context)
                break
            }
        }
    }

    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    deinit {
        self.patternLoad?.dispose()
    }

    private func loadPattern(_ file: TelegramMediaFile, context: AccountContext) {
        for index in 0 ..< VisualGramPatternMotion.count {
            let particle = CALayer()
            particle.contentsGravity = .resizeAspect
            particle.opacity = index.isMultiple(of: 2) ? 0.42 : 0.27
            self.layer.insertSublayer(particle, below: self.icon)
            self.patternLayers.append(particle)
        }
        let target = PatternContentsTarget { [weak self] _ in self?.updatePatternImage() }
        self.patternImage = target
        let itemId = file.resource.id.stringRepresentation
        let pixelSize = CGSize(width: 48, height: 48)
        if context.animationRenderer.loadFirstFrameSynchronously(target: target, cache: context.animationCache, itemId: itemId, size: pixelSize) {
            self.updatePatternImage()
        } else {
            self.patternLoad = context.animationRenderer.loadFirstFrame(
                target: target, cache: context.animationCache, itemId: itemId, size: pixelSize,
                fetch: animationCacheFetchFile(context: context, userLocation: .other, userContentType: .sticker, resource: .media(media: .standalone(media: file), resource: file.resource), type: AnimationCacheAnimationType(file: file), keyframeOnly: false, customColor: .white),
                completion: { [weak self] _, _ in self?.updatePatternImage() }
            )
        }
    }

    private func updatePatternImage() {
        for particle in self.patternLayers {
            particle.contents = self.patternImage?.contents
        }
    }

    func resetPatternMotion() {
        self.slosh = VisualGramPatternMotion()
        self.lastPosition = nil
        self.lastVelocity = .zero
    }

    func updatePatternMotion(position: CGPoint, delta: CGFloat) {
        guard !self.patternLayers.isEmpty else { return }
        if let previous = self.lastPosition, delta > 0 {
            let velocity = CGPoint(x: (position.x - previous.x) / delta, y: (position.y - previous.y) / delta)
            let acceleration = CGPoint(x: (velocity.x - self.lastVelocity.x) / delta, y: (velocity.y - self.lastVelocity.y) / delta)
            self.slosh.advance(delta: delta, acceleration: acceleration)
            self.lastVelocity = velocity
        }
        if delta > 0 || self.lastPosition == nil { self.lastPosition = position }
        let radius = self.bounds.width * 0.5
        for (index, particle) in self.patternLayers.enumerated() {
            let angle = self.slosh.angles[index]
            let distance = radius * (index.isMultiple(of: 2) ? 0.79 : 0.72)
            let side = radius * (index.isMultiple(of: 2) ? 0.26 : 0.21)
            particle.bounds = CGRect(x: 0, y: 0, width: side, height: side)
            particle.position = CGPoint(x: radius + sin(angle) * distance, y: radius + cos(angle) * distance)
            particle.setAffineTransform(CGAffineTransform(rotationAngle: -angle * 0.72))
        }
    }

    func updateGlass(diameter: CGFloat, isDark: Bool) {
        guard self.bounds.width != diameter || self.dark != isDark else { return }
        self.dark = isDark
        self.bounds = CGRect(x: 0, y: 0, width: diameter, height: diameter)
        self.layer.cornerRadius = diameter * 0.5
        self.glass.frame = self.bounds
        self.glass.update(size: self.bounds.size, cornerRadius: diameter * 0.5, isDark: isDark, tintColor: .init(kind: .custom(style: .clear, color: self.tint.withAlphaComponent(0.14))), transition: .immediate)
        self.highlight.frame = self.bounds
        self.highlight.cornerRadius = diameter * 0.5
        self.rim.frame = self.bounds
        self.rim.path = UIBezierPath(ovalIn: self.bounds.insetBy(dx: 0.5, dy: 0.5)).cgPath
        let iconSize = diameter * 0.64
        self.icon.bounds = CGRect(x: 0, y: 0, width: iconSize, height: iconSize)
        self.icon.position = CGPoint(x: self.bounds.midX, y: self.bounds.midY)
    }

    override func accessibilityActivate() -> Bool {
        guard let open = self.open else { return false }
        open(self.gift)
        return true
    }
}
