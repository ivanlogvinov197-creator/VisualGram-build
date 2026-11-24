import CodeInputView
import Display
import SwiftUI
import TelegramPresentationData
import UIKit

@MainActor
public enum DuckGramLocalAccounts {
    public static func open(from navigation: NavigationController, theme: PresentationTheme, prefilledNumber: String? = nil) {
        guard !(navigation.topViewController is DuckGramLocalAccountsController) else { return }
        navigation.view.endEditing(true)
        navigation.pushViewController(DuckGramLocalAccountsController(
            store: .shared, theme: theme, prefilledNumber: prefilledNumber
        ))
    }

    @discardableResult
    public static func restore(from navigation: NavigationController, theme: PresentationTheme) -> Bool {
        guard navigation.viewIfLoaded?.window != nil, navigation.topViewController != nil,
              navigation.presentedViewController == nil,
              let snapshot = try? DuckGramLocalAccountStore.shared.snapshot(),
              snapshot.activeNumber != nil else { return false }
        Self.open(from: navigation, theme: theme)
        return true
    }
}

private final class DuckGramLocalAccountsController: ViewController {
    private let store: DuckGramLocalAccountStore
    private let theme: PresentationTheme
    private let prefilledNumber: String?

    init(store: DuckGramLocalAccountStore, theme: PresentationTheme, prefilledNumber: String?) {
        self.store = store
        self.theme = theme
        self.prefilledNumber = prefilledNumber
        super.init(navigationBarPresentationData: nil)
    }

    required init(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    override func viewDidLoad() {
        super.viewDidLoad()
        let host = UIHostingController(rootView: DuckGramLocalAccountsView(
            store: self.store, theme: self.theme, prefilledNumber: self.prefilledNumber, close: { [weak self] in
                self?.dismiss()
            }
        ))
        self.addChild(host)
        host.view.translatesAutoresizingMaskIntoConstraints = false
        self.view.addSubview(host.view)
        NSLayoutConstraint.activate([
            host.view.topAnchor.constraint(equalTo: self.view.topAnchor),
            host.view.bottomAnchor.constraint(equalTo: self.view.bottomAnchor),
            host.view.leadingAnchor.constraint(equalTo: self.view.leadingAnchor),
            host.view.trailingAnchor.constraint(equalTo: self.view.trailingAnchor)
        ])
        host.didMove(toParent: self)
    }
}

private struct DuckGramLocalAccountsView: View {
    private enum Screen: Equatable {
        case number
        case code(number: String, fromPhoneEntry: Bool)
        case chats
        case conversation(String)
    }

    private let store: DuckGramLocalAccountStore
    private let theme: PresentationTheme
    private let close: () -> Void
    @State private var snapshot: DuckGramLocalAccountStore.Snapshot?
    @State private var screen: Screen
    @State private var number: String
    @State private var draft = ""
    @State private var errorMessage = ""
    @State private var showingError = false
    init(store: DuckGramLocalAccountStore, theme: PresentationTheme, prefilledNumber: String?, close: @escaping () -> Void) {
        self.store = store
        self.theme = theme
        self.close = close
        let snapshot = try? store.snapshot()
        self._snapshot = State(initialValue: snapshot)
        self._number = State(initialValue: prefilledNumber ?? "+888")
        if let prefilledNumber {
            self._screen = State(initialValue: .code(number: prefilledNumber, fromPhoneEntry: true))
        } else {
            self._screen = State(initialValue: snapshot?.activeNumber == nil ? .number : .chats)
        }
    }

    var body: some View {
        VStack(spacing: 0) {
            self.header
            Divider()
            switch self.screen {
            case .number:
                self.numberForm
            case let .code(number, _):
                self.codeEntry(number: number)
            case .chats:
                self.chatList
            case let .conversation(recipient):
                if let own = self.snapshot?.activeNumber {
                    self.conversation(own: own, recipient: recipient)
                }
            }
        }
        .background(Color(uiColor: .systemGroupedBackground))
        .alert("Ошибка", isPresented: self.$showingError) {
            Button("ОК", role: .cancel) {}
        } message: {
            Text(self.errorMessage)
        }
    }

    private var isCodeEntry: Bool {
        if case .code = self.screen { return true }
        return false
    }

    private var header: some View {
        HStack(spacing: 14) {
            if self.isCodeEntry || (self.screen != .chats && self.snapshot?.activeNumber != nil) {
                Button(action: self.goBack) {
                    Image(systemName: "chevron.left")
                        .frame(width: 44, height: 44)
                }
                .accessibilityLabel("Назад")
            }
            Text(self.title)
                .font(.headline)
                .accessibilityAddTraits(.isHeader)
                .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
            if !self.isCodeEntry {
                Button(action: self.exit) {
                    Image(systemName: "xmark.circle.fill")
                        .font(.title3)
                        .frame(width: 44, height: 44)
                }
                .accessibilityLabel("Закрыть")
            }
        }
        .padding(.horizontal, 14)
        .background(Color(uiColor: self.theme.list.plainBackgroundColor))
    }

    private var title: String {
        switch self.screen {
        case .number: return "Вход"
        case .code: return "Код входа"
        case .chats: return "Чаты"
        case let .conversation(recipient): return recipient
        }
    }

    private var numberForm: some View {
        Form {
            Section {
                TextField("Номер телефона", text: self.$number)
                    .keyboardType(.phonePad)
                Button("Далее", action: self.continueWithNumber)
            }
            if let profiles = self.snapshot?.profiles, !profiles.isEmpty {
                Section("Аккаунты") {
                    ForEach(profiles, id: \.self) { profile in
                        Button(profile) {
                            self.number = profile
                            self.continueWithNumber()
                        }
                    }
                }
            }
        }
    }

    private func codeEntry(number: String) -> some View {
        ScrollView {
            VStack(spacing: 14) {
                Text("Введите код")
                    .font(.largeTitle.weight(.semibold))
                    .accessibilityAddTraits(.isHeader)
                Text(number)
                    .font(.title3)
                DuckGramCodeInput(theme: self.theme) { code in
                    self.signIn(number: number, code: code)
                }
                .id(number)
                .frame(height: 51)
                .padding(.top, 8)
                Text("Подойдёт любая комбинация из пяти цифр.")
                    .font(.subheadline)
                    .foregroundStyle(Color(uiColor: self.theme.list.itemSecondaryTextColor))
            }
            .multilineTextAlignment(.center)
            .foregroundStyle(Color(uiColor: self.theme.list.itemPrimaryTextColor))
            .frame(maxWidth: 430)
            .padding(.vertical, 36)
            .padding(.horizontal, 16)
            .frame(maxWidth: .infinity)
        }
        .background(Color(uiColor: self.theme.list.plainBackgroundColor))
    }

    private var chatList: some View {
        List {
            if let snapshot = self.snapshot, let own = snapshot.activeNumber {
                Section("Текущий профиль") {
                    Text(own)
                    Button("Добавить или сменить профиль") {
                        self.number = "+888"
                        self.screen = .number
                    }
                }
                Section("Личные чаты") {
                    let contacts = snapshot.profiles.filter { $0 != own }
                    if contacts.isEmpty {
                        Text("Добавь ещё один аккаунт, чтобы начать переписку.")
                            .foregroundStyle(.secondary)
                    }
                    ForEach(contacts, id: \.self) { contact in
                        Button {
                            self.draft = ""
                            self.screen = .conversation(contact)
                        } label: {
                            VStack(alignment: .leading, spacing: 4) {
                                Text(contact)
                                if let last = snapshot.messages(between: own, and: contact).last {
                                    Text(last.text).font(.subheadline).foregroundStyle(.secondary).lineLimit(1)
                                }
                            }
                            .frame(maxWidth: .infinity, alignment: .leading)
                        }
                    }
                }
            }
        }
        .listStyle(.insetGrouped)
    }

    private func conversation(own: String, recipient: String) -> some View {
        let messages = self.snapshot?.messages(between: own, and: recipient) ?? []
        return VStack(spacing: 0) {
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(spacing: 8) {
                        if messages.isEmpty {
                            Text("Здесь появится переписка.")
                                .font(.subheadline)
                                .foregroundStyle(.secondary)
                        }
                        ForEach(messages) { message in
                            let outgoing = message.sender == own
                            VStack(alignment: .leading, spacing: 3) {
                                Text(message.text).textSelection(.enabled)
                                Text(message.date, style: .time).font(.caption2).foregroundStyle(.secondary)
                            }
                            .padding(10)
                            .background(outgoing ? Color.accentColor.opacity(0.14) : Color(uiColor: .secondarySystemGroupedBackground))
                            .clipShape(RoundedRectangle(cornerRadius: 12))
                            .frame(maxWidth: .infinity, alignment: outgoing ? .trailing : .leading)
                        }
                        Color.clear.frame(height: 1).id("latest")
                    }
                    .padding(14)
                }
                .task(id: messages.last?.id) {
                    await Task.yield()
                    proxy.scrollTo("latest", anchor: .bottom)
                }
            }
            Divider()
            HStack {
                TextField("Сообщение", text: self.$draft)
                    .textFieldStyle(.roundedBorder)
                    .submitLabel(.send)
                    .onSubmit { self.send(from: own, to: recipient) }
                Button {
                    self.send(from: own, to: recipient)
                } label: {
                    Image(systemName: "arrow.up.circle.fill")
                        .font(.title2)
                        .frame(width: 44, height: 44)
                }
                .accessibilityLabel("Отправить")
                .disabled(self.draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            }
            .padding(.horizontal, 14)
            .background(Color(uiColor: .systemBackground))
        }
    }

    private func showChats() {
        self.draft = ""
        self.screen = .chats
    }

    private func goBack() {
        switch self.screen {
        case .code(_, true): self.close()
        case .code(_, false): self.screen = .number
        case .number, .conversation: self.showChats()
        case .chats: break
        }
    }

    private func continueWithNumber() {
        guard let number = DuckGramLocalAccountStore.localNumber(self.number) else {
            self.showError("Введи номер с префиксом +888.")
            return
        }
        self.screen = .code(number: number, fromPhoneEntry: false)
    }

    private func signIn(number: String, code: String) -> Bool {
        do {
            self.snapshot = try self.store.signIn(number: number, code: code)
            self.showChats()
            return true
        } catch {
            self.showError("Не удалось сохранить профиль.")
            return false
        }
    }

    private func send(from own: String, to recipient: String) {
        do {
            self.snapshot = try self.store.send(text: self.draft, from: own, to: recipient)
            self.draft = ""
        } catch DuckGramLocalAccountStore.InputError.emptyMessage {
            return
        } catch {
            self.showError("Не удалось сохранить сообщение.")
        }
    }

    private func exit() {
        do {
            if self.snapshot?.activeNumber != nil {
                try self.store.signOut()
            }
            self.close()
        } catch {
            self.showError("Не удалось выйти из аккаунта.")
        }
    }

    private func showError(_ text: String) {
        self.errorMessage = text
        self.showingError = true
    }
}

private struct DuckGramCodeInput: UIViewRepresentable {
    let theme: PresentationTheme
    let complete: (String) -> Bool

    func makeUIView(context: Context) -> DuckGramCodeInputHost {
        DuckGramCodeInputHost(theme: self.theme)
    }

    func updateUIView(_ view: DuckGramCodeInputHost, context: Context) {
        view.complete = self.complete
    }
}

private final class DuckGramCodeInputHost: UIView {
    private let input = CodeInputView()
    private let theme: CodeInputView.Theme
    private var requestedFocus = false
    var complete: ((String) -> Bool)?

    init(theme: PresentationTheme) {
        self.theme = CodeInputView.Theme(
            inactiveBorder: theme.list.itemPlainSeparatorColor.argb,
            activeBorder: theme.list.itemAccentColor.argb,
            succeedBorder: theme.list.itemDisclosureActions.constructive.fillColor.argb,
            failedBorder: theme.list.itemDestructiveColor.argb,
            foreground: theme.list.itemPrimaryTextColor.argb,
            isDark: theme.overallDarkAppearance
        )
        super.init(frame: .zero)
        self.input.textField.textContentType = nil
        self.input.textField.accessibilityLabel = "Код"
        self.addSubview(self.input.view)
        self.input.updated = { [weak self] in
            guard let self, let complete = self.complete, DuckGramLocalAccountStore.isValidCode(self.input.text) else {
                return
            }
            if complete(self.input.text) {
                self.input.text = ""
                _ = self.input.resignFirstResponder()
            } else {
                self.input.animateError()
            }
        }
    }

    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    override func didMoveToWindow() {
        super.didMoveToWindow()
        guard self.window != nil, !self.requestedFocus else { return }
        self.requestedFocus = true
        DispatchQueue.main.async { [weak self] in
            guard let self, self.window != nil else { return }
            _ = self.input.becomeFirstResponder()
        }
    }

    override func layoutSubviews() {
        super.layoutSubviews()
        guard self.bounds.width > 0 else { return }
        let size = self.input.update(theme: self.theme, prefix: "", count: DuckGramLocalAccountStore.codeLength,
                                     width: self.bounds.width, compact: self.bounds.width < 275)
        self.input.frame = CGRect(x: 0, y: (self.bounds.height - size.height) / 2, width: size.width, height: size.height)
    }
}
