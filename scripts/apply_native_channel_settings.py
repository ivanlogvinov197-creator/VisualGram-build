"""Connect local channel settings to native broadcast-channel profile surfaces."""
import shutil

from prepare_native import replace


def apply_channel_settings(root, project):
    sources = root / "submodules/TelegramUI/Components/PeerInfo/PeerInfoScreen/Sources"
    shutil.copyfile(
        project / "native/VisualGramChannelSettingsController.swift",
        sources / "VisualGramChannelSettingsController.swift",
    )

    data = sources / "PeerInfoData.swift"
    replace(
        data,
        """        case .channel:
            let status = context.account.viewTracker.peerView(peerId, updateData: false)
            |> map { peerView -> PeerInfoStatusData? in
                guard let _ = peerView.peers[peerId] as? TelegramChannel else {
                    return PeerInfoStatusData(text: strings.Channel_Status, isActivity: false, key: nil)
                }
""",
        """        case .channel:
            let status = combineLatest(
                context.account.viewTracker.peerView(peerId, updateData: false),
                VisualGramLocalAppearance.shared.changes
            )
            |> map { peerView, _ -> PeerInfoStatusData? in
                guard let channel = peerView.peers[peerId] as? TelegramChannel else {
                    return PeerInfoStatusData(text: strings.Channel_Status, isActivity: false, key: nil)
                }
                if case .broadcast = channel.info,
                   let count = VisualGramLocalAppearance.shared.visualChannel(accountId: context.account.peerId, sourcePeerId: peerId)?.subscriberCountOverride {
                    return PeerInfoStatusData(text: strings.Conversation_StatusSubscribers(count), isActivity: false, key: nil)
                }
""",
    )

    items = sources / "PeerInfoProfileItems.swift"
    replace(
        items,
        """        let ItemPeerPersonalChannel = 11
        let ItemCommunity = 12
""",
        """        let ItemPeerPersonalChannel = 11
        let ItemCommunity = 12

        if data.threadData == nil, case .broadcast = channel.info,
           VisualGramLocalAppearance.shared.visualChannel(accountId: context.account.peerId, sourcePeerId: channel.id)?.isCopied == true {
            items[.peerSettings]!.append(PeerInfoScreenDisclosureItem(
                id: "visual-gram-channel-posts",
                text: "Визуальный канал",
                icon: PresentationResourcesSettings.channels,
                action: {
                    interaction.getController()?.push(visualGramChannelPostsController(context: context, sourcePeerId: channel.id))
                }
            ))
            items[.peerSettings]!.append(PeerInfoScreenDisclosureItem(
                id: "visual-gram-channel-settings",
                text: "Настройки визуального канала",
                icon: PresentationResourcesSettings.chatAppearance,
                action: {
                    interaction.getController()?.push(visualGramChannelSettingsController(context: context, sourcePeerId: channel.id))
                }
            ))
        }
""",
    )
    replace(
        items,
        "                let ItemWelcomeMessages = 20\n",
        """                let ItemWelcomeMessages = 20

                if VisualGramLocalAppearance.shared.visualChannel(accountId: context.account.peerId, sourcePeerId: channel.id)?.isCopied == true {
                    items[.peerSettings]!.append(PeerInfoScreenDisclosureItem(
                        id: "visual-gram-channel-settings",
                        text: "Настройки визуального канала",
                        icon: PresentationResourcesSettings.chatAppearance,
                        action: {
                            interaction.getController()?.push(visualGramChannelSettingsController(context: context, sourcePeerId: channel.id))
                        }
                    ))
                }

""",
    )
