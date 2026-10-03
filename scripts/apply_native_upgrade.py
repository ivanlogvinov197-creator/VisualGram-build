"""Connect local gift upgrades to Telegram's stock reveal animation."""
from prepare_native import replace


def apply_upgrade(root):
    path = root / "submodules/TelegramUI/Components/Gifts/GiftViewScreen/Sources/GiftViewScreen.swift"
    replace(path, '        private func fetchUpgradeForm() {\n', '        private func fetchUpgradeForm() {\n            guard !self.isVisualGramGift else { return }\n')
    replace(path, '        func commitUpgrade() {\n            guard !self.isVisualGramGift else { return }\n', '''        func commitUpgrade() {
            if self.isVisualGramGift, let arguments = self.subject.arguments, case .generic = arguments.gift {
                guard !self.inProgress, let reference = arguments.reference,
                      case let .message(messageId) = reference, let preview = self.upgradePreview,
                      let result = VisualGramLocalAppearance.shared.upgradeLocalGift(accountId: self.context.account.peerId, reference: reference, preview: preview, keepOriginalInfo: self.keepOriginalInfo) else { return }
                self.subject = .profileGift(messageId.peerId, result)
                self.testUpgradeAnimation = true
                self.revealedAttributes.removeAll()
                self.commitUpgrade()
                return
            }
            guard !self.isVisualGramGift || self.testUpgradeAnimation else { return }
''')
    replace(path, '                let buttonTitle = subject.arguments?.upgradeStars != nil ? strings.Gift_Upgrade_Confirm : upgradeString\n', '''                if state.isVisualGramGift { upgradeString = strings.Gift_Upgrade_Upgrade }
                let buttonTitle = subject.arguments?.upgradeStars != nil ? strings.Gift_Upgrade_Confirm : upgradeString
''')
    replace(path, '            if !canUpgrade, let gift = state.starGiftsMap[giftId], let _ = gift.upgradeStars {\n', '''            if VisualGramLocalAppearance.isLocalReference(subject.arguments?.reference) {
                incoming = true
                canGiftUpgrade = false
            }
            if !canUpgrade, let gift = state.starGiftsMap[giftId], let _ = gift.upgradeStars {
''')
