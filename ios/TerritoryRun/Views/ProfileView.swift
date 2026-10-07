import SwiftUI
import UserNotifications

@MainActor
struct ProfileView: View {
    @ObservedObject var store: AppStore
    @ObservedObject var queue: UploadQueue
    @State private var confirmSignOut = false
    @State private var showDeletion = false
    init(store: AppStore) { self.store = store; self.queue = store.queue }

    var body: some View {
        NavigationStack {
            List {
                Section {
                    HStack(spacing: 16) {
                        Image(systemName: "figure.run.circle.fill").font(.system(size: 54)).foregroundStyle(.mint)
                        VStack(alignment: .leading, spacing: 6) {
                            Text(store.user?.displayName ?? "Runner").font(.title2.bold())
                            Text("@\(store.user?.username ?? "")").foregroundStyle(.secondary)
                        }
                    }.padding(.vertical, 8)
                    stat("Your ground", Display.area(store.stats.areaM2))
                    stat("Expiring within 3 days", Display.area(store.stats.expiringAreaM2))
                    stat("Runs recorded", "\(store.stats.runCount)")
                    stat("Distance run", Display.distance(store.stats.distanceM))
                }
                Section("Weekly goal") {
                    WeeklyGoalView(goals: store.goals)
                }
                Section("Sync") {
                    Label(store.connected ? "Connected to the server" : "Server not reachable", systemImage: store.connected ? "checkmark.circle.fill" : "wifi.slash")
                    Text(store.api.server).font(.caption).foregroundStyle(.secondary).textSelection(.enabled)
                    if let message = store.syncMessage { Text(message).font(.caption).foregroundStyle(.secondary) }
                    stat("Saved runs waiting", "\(queue.pending.count)")
                    Button(store.syncing ? "Syncing…" : "Sync now") { Task { await store.sync(force: true) } }.disabled(store.syncing)
                }
                Section {
                    if store.feed.isEmpty {
                        Text("When a friend captures your territory, you'll hear about it here.").font(.subheadline).foregroundStyle(.secondary)
                    }
                    ForEach(store.feed) { item in
                        HStack(alignment: .top) {
                            Circle().fill(item.readAt == nil ? Color.mint : .clear).frame(width: 7, height: 7).padding(.top, 7)
                            VStack(alignment: .leading, spacing: 6) {
                                Text(item.title).font(.headline)
                                Text(item.body).font(.subheadline).foregroundStyle(.secondary)
                                Text(item.createdAt.formatted(date: .abbreviated, time: .shortened)).font(.caption2).foregroundStyle(.tertiary)
                            }
                        }.padding(.vertical, 5)
                    }
                    if !store.feed.isEmpty { Button("Mark all as read") { Task { await store.markRead() } } }
                } header: { Text("Activity") }
                if (Bundle.main.object(forInfoDictionaryKey: "PushEnabled") as? String) == "YES" {
                    Button("Enable push alerts") {
                        Task {
                            do {
                                let granted = try await UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .badge, .sound])
                                if granted { UIApplication.shared.registerForRemoteNotifications() }
                            } catch { store.error = error.localizedDescription }
                        }
                    }
                }
                Section {
                    Text("Run a closed loop to claim land. Revisit your territory to renew it. Friends can take overlapping ground once its protection ends.")
                        .font(.caption).foregroundStyle(.secondary)
                    NavigationLink("Privacy and data") { PrivacyView() }
                    Button("Delete account", role: .destructive) { showDeletion = true }.disabled(store.syncing)
                    Button("Sign out", role: .destructive) { confirmSignOut = true }.disabled(store.syncing || store.tracker.active)
                }
            }.navigationTitle("You").refreshable { await store.refreshAll() }
                .sheet(isPresented: $showDeletion) { AccountDeletionView(store: store) }
                .confirmationDialog("Sign out?", isPresented: $confirmSignOut, titleVisibility: .visible) {
                    Button("Sign out", role: .destructive) { Task { await store.signOut() } }
                    Button("Cancel", role: .cancel) {}
                } message: { Text("Unsynced runs remain on this phone for this account. Sign back into the same server to upload them.") }
        }
    }
    private func stat(_ label: String, _ value: String) -> some View {
        HStack { Text(label).foregroundStyle(.secondary); Spacer(); Text(value).fontWeight(.semibold) }
    }
}
