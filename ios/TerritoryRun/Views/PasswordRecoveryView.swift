import SwiftUI

@MainActor
struct PasswordRecoveryView: View {
    let server: String
    @Environment(\.dismiss) private var dismiss
    @State private var email = ""
    @State private var message: String?
    @State private var failure: String?
    @State private var busy = false

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    Text("Enter the email you used to create your account. Open the recovery link to choose a new password, then return here to sign in.")
                    TextField("Email", text: $email)
                        .keyboardType(.emailAddress).textContentType(.emailAddress)
                        .textInputAutocapitalization(.never).autocorrectionDisabled()
                        .disabled(busy)
                    Button {
                        busy = true
                        failure = nil
                        Task {
                            do {
                                let client = APIClient()
                                try client.setServer(server)
                                message = try await client.requestPasswordRecovery(email: email)
                            } catch { failure = error.localizedDescription }
                            busy = false
                        }
                    } label: {
                        if busy { ProgressView("Requesting link") }
                        else { Text("Send recovery link") }
                    }.disabled(busy || email.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || message != nil)
                }
                if let message { Section { Text(message).accessibilityIdentifier("recoveryAcknowledgement") } }
                if let failure { Section { Text(failure).foregroundStyle(.red) } }
                Section {
                    Text("Resetting your password signs out your devices. Runs saved on your phone stay there; sign in to the same account to sync them.")
                }
            }
            .navigationTitle("Recover account")
            .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Done") { dismiss() } } }
            .interactiveDismissDisabled(busy)
        }
    }
}
