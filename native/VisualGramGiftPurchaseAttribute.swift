import Foundation
import Postbox

// Only attached to synthetic, in-memory chat entries. Never written to Postbox.
public final class VisualGramGiftPurchaseAttribute: MessageAttribute {
    public let grams: Int64?
    public let stars: Int64

    public init(stars: Int64, grams: Int64? = nil) { self.stars = stars; self.grams = grams }
    public init(decoder: PostboxDecoder) { self.stars = decoder.decodeInt64ForKey("s", orElse: 0); self.grams = decoder.decodeOptionalInt64ForKey("g") }
    public func encode(_ encoder: PostboxEncoder) { encoder.encodeInt64(self.stars, forKey: "s"); if let grams { encoder.encodeInt64(grams, forKey: "g") } }
}
