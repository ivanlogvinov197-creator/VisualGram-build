import Foundation

struct VisualGramOrbitRelease {
    let phaseOffset: CGFloat
    let angularVelocity: CGFloat
    let offset: CGPoint
    let residualVelocity: CGPoint

    init(position: CGPoint, velocity: CGPoint, center: CGPoint, radii: CGSize, baseAngle: CGFloat, previousAngle: CGFloat) {
        let nx = (position.x - center.x) / radii.width
        let ny = (position.y - center.y) / radii.height
        let angle = hypot(nx, ny) < 0.12 ? previousAngle : atan2(ny, nx)
        self.phaseOffset = angle - baseAngle
        self.offset = CGPoint(x: position.x - center.x - cos(angle) * radii.width, y: position.y - center.y - sin(angle) * radii.height)
        let tangentX = -sin(angle) * radii.width
        let tangentY = cos(angle) * radii.height
        let projected = (velocity.x * tangentX + velocity.y * tangentY) / max(1, tangentX * tangentX + tangentY * tangentY)
        self.angularVelocity = min(9, max(-9, projected))
        self.residualVelocity = CGPoint(x: velocity.x - tangentX * self.angularVelocity, y: velocity.y - tangentY * self.angularVelocity)
    }
}

// Angles are measured from the bottom of the sphere. Each pattern mark moves
// along the inner surface under gravity and the acceleration of the shell.
struct VisualGramPatternMotion {
    static let count = 7
    private static let restingAngles = [-1.31, -0.87, -0.43, 0, 0.43, 0.87, 1.31] as [CGFloat]
    private(set) var angles = restingAngles
    private var velocities = Array(repeating: CGFloat.zero, count: count)

    mutating func advance(delta: CGFloat, acceleration: CGPoint) {
        let dt = min(1.0 / 30.0, max(0, delta))
        let ax = min(11, max(-11, acceleration.x / 420))
        let ay = min(9, max(-9, acceleration.y / 420))
        for index in self.angles.indices {
            let angle = self.angles[index]
            let gravity = -12 * sin(angle - Self.restingAngles[index])
            let inertia = -ax * cos(angle) + ay * sin(angle)
            self.velocities[index] = (self.velocities[index] + (gravity + inertia) * dt) * exp(-2.7 * dt)
            self.angles[index] += self.velocities[index] * dt
        }
        // Keep neighbouring pieces from overtaking one another during a flick.
        for right in 1 ..< self.angles.count {
            let gap = self.angles[right] - self.angles[right - 1]
            if gap < 0.18 {
                let correction = (0.18 - gap) * 0.5
                self.angles[right - 1] -= correction
                self.angles[right] += correction
            }
        }
    }
}
