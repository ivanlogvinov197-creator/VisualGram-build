"""Add on-device +888 profiles without changing Telegram authorization."""
import shutil

from prepare_native import replace


def apply_local_accounts(root, project):
    submodules = root / "submodules"
    authorization = submodules / "AuthorizationUI/Sources"
    for name in ("DuckGramLocalAccountStore.swift", "DuckGramLocalAccountsController.swift"):
        shutil.copyfile(project / "native" / name, authorization / name)

    phone = authorization / "AuthorizationSequencePhoneEntryController.swift"
    replace(phone, """        let (_, _, number) = self.controllerNode.codeAndNumber
        if !number.isEmpty {
""", """        let enteredNumber = self.controllerNode.currentNumber
        if enteredNumber.hasPrefix("+888") {
            guard let number = DuckGramLocalAccountStore.localNumber(enteredNumber) else {
                self.hapticFeedback.error()
                self.controllerNode.animateError()
                return
            }
            guard let navigation = self.navigationController as? NavigationController else { return }
            DuckGramLocalAccounts.open(from: navigation, theme: self.presentationData.theme, prefilledNumber: number)
            return
        }
        let (_, _, number) = self.controllerNode.codeAndNumber
        if !number.isEmpty {
""")

    sequence = authorization / "AuthorizationSequenceController.swift"
    replace(sequence, """        if !self.didPlayPresentationAnimation {
            self.didPlayPresentationAnimation = true
            self.animateIn()
        }
""", """        if !self.didPlayPresentationAnimation {
            self.didPlayPresentationAnimation = true
            self.animateIn()
        }
        Queue.mainQueue().async { [weak self] in
            if let self { DuckGramLocalAccounts.restore(from: self, theme: self.presentationData.theme) }
        }
""")

    root_controller = submodules / "TelegramUI/Sources/TelegramRootController.swift"
    replace(root_controller, "import TooltipUI\n", "import TooltipUI\nimport AuthorizationUI\n")
    replace(root_controller, """        Queue.mainQueue().async { [weak self] in
            let defaults = UserDefaults.standard
""", """        Queue.mainQueue().async { [weak self] in
            if let self, DuckGramLocalAccounts.restore(from: self, theme: self.presentationData.theme) { return }
            let defaults = UserDefaults.standard
""")
    replace(root_controller, "            self.pushViewController(visualGramAppearanceController(context: self.context))\n", """            let menu = visualGramAppearanceController(context: self.context, openLocalAccounts: { [weak self] in
                if let self { DuckGramLocalAccounts.open(from: self, theme: self.presentationData.theme) }
            })
            self.pushViewController(menu)
""")
