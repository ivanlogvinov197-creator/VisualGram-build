import Foundation
#if canImport(CoreGraphics)
import CoreGraphics
#endif

@main
struct ProfileGiftMotionTests {
    static func main() {
        let center = CGPoint(x: 200, y: 130)
        let radii = CGSize(width: 130, height: 40)
        for direction: CGFloat in [-1, 1] {
            let release = VisualGramOrbitRelease(position: CGPoint(x: 330, y: 130), velocity: CGPoint(x: 30, y: 240 * direction), center: center, radii: radii, baseAngle: 0.2, previousAngle: 0.4)
            precondition(abs(release.angularVelocity - 6 * direction) < 0.001)
            precondition(hypot(release.offset.x, release.offset.y) < 0.001)
            precondition(abs(release.residualVelocity.x - 30) < 0.001 && abs(release.residualVelocity.y) < 0.001)
        }
        // Releasing over the profile's details must start at the finger without
        // jumping back to the edge of the header.
        let point = CGPoint(x: 104, y: 402)
        let release = VisualGramOrbitRelease(position: point, velocity: CGPoint(x: 800, y: -200), center: center, radii: radii, baseAngle: 2, previousAngle: 1)
        let angle = 2 + release.phaseOffset
        precondition(abs(point.x - center.x - cos(angle) * radii.width - release.offset.x) < 0.001)
        precondition(abs(point.y - center.y - sin(angle) * radii.height - release.offset.y) < 0.001)
        let centered = VisualGramOrbitRelease(position: center, velocity: .zero, center: center, radii: radii, baseAngle: 1, previousAngle: -1)
        precondition(abs(centered.phaseOffset + 2) < 0.001)
        for fps: CGFloat in [30, 60, 120] {
            var motion = VisualGramPatternMotion()
            let rest = motion.angles
            for _ in 0 ..< Int(fps / 2) {
                motion.advance(delta: 1 / fps, acceleration: CGPoint(x: 4000, y: 2000))
            }
            precondition(motion.angles[3] < -0.3)
            for _ in 0 ..< Int(fps * 7) {
                motion.advance(delta: 1 / fps, acceleration: .zero)
                precondition(zip(motion.angles, motion.angles.dropFirst()).allSatisfy { $0 < $1 })
            }
            precondition(zip(motion.angles, rest).allSatisfy { abs($0 - $1) < 0.002 })
        }
        print("Profile gift motion checks passed")
    }
}
