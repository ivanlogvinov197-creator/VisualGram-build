"""Show subscriber overrides on both native channel chat headers."""

from prepare_native import replace


def apply_channel_chat(root):
    title_sources = root / "submodules/TelegramUI/Components/ChatTitleView/Sources"
    for filename, indent, account, strings, color in (
        (
            "ChatTitleComponent.swift",
            "                                ",
            "component.context.account.peerId",
            "component.strings",
            "component.theme.chat.inputPanel.inputControlColor",
        ),
        (
            "ChatTitleView.swift",
            "                                    ",
            "self.context.account.peerId",
            "strings",
            "titleTheme.rootController.navigationBar.secondaryTextColor",
        ),
    ):
        original = indent + "if channel.isForumOrMonoForum, customTitle != nil {\n"
        insert = (
            indent + "if case .broadcast = channel.info, let count = VisualGramLocalAppearance.shared"
            f".visualChannel(accountId: {account}, sourcePeerId: peerView.peerId)?.subscriberCountOverride {{\n"
            + indent + f"    let string = NSAttributedString(string: {strings}.Conversation_StatusSubscribers(count), font: subtitleFont, textColor: {color})\n"
            + indent + "    state = .info(string, .generic)\n"
            + indent + "} else if channel.isForumOrMonoForum, customTitle != nil {\n"
        )
        replace(title_sources / filename, original, insert)
