"""Connect local channel settings to native broadcast-channel profile surfaces."""

from prepare_native import replace


def apply_channel_settings(root):
    sources = root / "submodules/TelegramUI/Components/PeerInfo/PeerInfoScreen/Sources"
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

    replace(data, """            return context.engine.data.subscribe(
                TelegramEngine.EngineData.Item.Peer.PersonalChannel(id: peerId)
            )
""", """            let nativeChannel = context.engine.data.subscribe(
                TelegramEngine.EngineData.Item.Peer.PersonalChannel(id: peerId)
            )
            guard peerId == context.account.peerId else { return nativeChannel }
            return combineLatest(nativeChannel, VisualGramLocalAppearance.shared.changes)
            |> map { original, _ in
                guard let selected = VisualGramLocalAppearance.shared.profileChannel(accountId: peerId) else {
                    return original
                }
                let count = VisualGramLocalAppearance.shared.visualChannel(accountId: peerId, sourcePeerId: selected)?.subscriberCountOverride
                return .known(TelegramPersonalChannel(peerId: selected, subscriberCount: count, topMessageId: nil))
            }
""")
    replace(data, """                if let participantCount {
                    mappedParticipantCount = participantCount
""", """                if let override = VisualGramLocalAppearance.shared.visualChannel(accountId: context.account.peerId, sourcePeerId: channelPeer.id)?.subscriberCountOverride {
                    mappedParticipantCount = Int(override)
                } else if let participantCount {
                    mappedParticipantCount = participantCount
""")
