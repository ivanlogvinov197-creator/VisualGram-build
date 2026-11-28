"""Enable selection in Telegram's existing gift variants browser."""
from prepare_native import replace


def apply_nft_selection(root):
    variants = root / "submodules/TelegramUI/Components/Gifts/GiftViewScreen/Sources/GiftUpgradeVariantsScreen.swift"
    signature = "public class GiftUpgradeVariantsScreen: ViewControllerComponentContainer {"
    replace(variants, signature, signature + """
    public var visualGramSelectAttributes: (([StarGift.UniqueGift.Attribute]) -> Void)?
""")
    replace(variants, '                if let selectedAttributes = component.selectedAttributes {', '''                if (environment.controller() as? GiftUpgradeVariantsScreen)?.visualGramSelectAttributes != nil {
                    self.isPlaying = false
                }
                if let selectedAttributes = component.selectedAttributes {''')
    replace(variants, '            let playbackButtonSize = self.playbackButton.update(', '''            let selecting = (environment.controller() as? GiftUpgradeVariantsScreen)?.visualGramSelectAttributes != nil
            let playbackContent: AnyComponent<Empty>
            if selecting {
                playbackContent = AnyComponent(MultilineTextComponent(text: .plain(NSAttributedString(string: environment.strings.Common_Done, font: Font.semibold(17.0), textColor: .white))))
            } else {
                playbackContent = AnyComponent(PlayButtonComponent(isPlay: !self.isPlaying, title: !self.isPlaying && self.showRandomizeTip ? environment.strings.Gift_Variants_Randomize : nil))
            }
            let playbackButtonSize = self.playbackButton.update(''')
    replace(variants, '''                    component: AnyComponentWithIdentity(id: "content", component: AnyComponent(
                        PlayButtonComponent(isPlay: !self.isPlaying, title: !self.isPlaying && self.showRandomizeTip ? environment.strings.Gift_Variants_Randomize : nil)
                    )),''', '''                    component: AnyComponentWithIdentity(id: selecting ? "select" : "content", component: playbackContent),''')
    replace(variants, '                        self.isPlaying = !self.isPlaying', '''                        if let controller = self.environment?.controller() as? GiftUpgradeVariantsScreen, let select = controller.visualGramSelectAttributes {
                            guard let model = self.selectedModel, let backdrop = self.selectedBackdrop, let symbol = self.selectedSymbol else { return }
                            controller.visualGramSelectAttributes = nil
                            controller.dismiss(completion: {
                                Queue.mainQueue().justDispatch { select([model, backdrop, symbol]) }
                            })
                            return
                        }
                        self.isPlaying = !self.isPlaying''')
