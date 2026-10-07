import SwiftUI

@MainActor
struct AccountDeletionView: View {
    @ObservedObject var store: AppStore
    var recovering = false
    @Environment(\.dismiss) private var dismiss
    @State private var password = ""
    @State private var confirm = false

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    Text("Delete your account, runs, territory, friendships and notifications from the active service. This also erases saved and unfinished runs for this account on this phone, including runs that have not uploaded.")
                    Text("This cannot be undone. Other runners keep the territory they have earned. Backup retention is described in the privacy policy.").foregroundStyle(.secondary)
                }
                if let problem = store.deletionRecoveryError {
                    Text(problem).foregroundStyle(.red)
                } else {
                    if recovering {
                        Section("Deletion in progress") {
                            Text(store.syncMessage ?? "Checking whether the server completed your request…")
                            Button("Check deletion status") { Task { await store.recoverDeletion() } }.disabled(store.syncing)
                        }
                    }
                    Section("Confirm your identity") {
                        SecureField("Current password", text: $password).textContentType(.password)
                        Button(store.syncing ? "Please wait…" : "Delete account permanently", role: .destructive) { confirm = true }
                            .disabled(password.isEmpty || store.syncing)
                    }
                    Text("You need a connection to the server. If the connection stops, reopen this app to check completion. Recording and uploads pause while deletion is pending.")
                        .font(.footnote).foregroundStyle(.secondary)
                }
                NavigationLink("Privacy and data") { PrivacyView() }
            }
            .navigationTitle("Delete account")
            .toolbar {
                if !recovering { ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } } }
            }
            .confirmationDialog("Permanently delete your account and all saved runs?", isPresented: $confirm, titleVisibility: .visible) {
                Button("Delete permanently", role: .destructive) {
                    let submittedPassword = password
                    password = ""
                    Task { await store.deleteAccount(password: submittedPassword) }
                }
            }
            .task { if recovering { await store.recoverDeletion() } }
        }
    }
}
