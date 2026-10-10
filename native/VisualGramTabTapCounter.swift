import Foundation

public struct VisualGramTabTapCounter {
    private var count = 0
    private var lastTap: Double?
    public init() {}
    public mutating func reset() { self.count = 0; self.lastTap = nil }
    public mutating func tap(now: Double) -> Bool {
        if let last = self.lastTap, now >= last, now - last <= 1.0 { self.count += 1 }
        else { self.count = 1 }
        self.lastTap = now
        if self.count == 3 { self.reset(); return true }
        return false
    }
}
