import Foundation
import Postbox

// Only attached to synthetic, in-memory chat entries. Never written to Postbox.
public final class VisualGramGiftPurchaseAttribute: MessageAttribute {
    public let stars: Int64

    public init(stars: Int64) { self.stars = stars }
    public init(decoder: PostboxDecoder) { self.stars = decoder.decodeInt64ForKey("s", orElse: 0) }
    public func encode(_ encoder: PostboxEncoder) { encoder.encodeInt64(self.stars, forKey: "s") }
}
