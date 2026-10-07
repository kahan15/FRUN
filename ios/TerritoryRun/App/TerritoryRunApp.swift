import SwiftUI
import UserNotifications

@main
@MainActor
struct TerritoryRunApp: App {
    @UIApplicationDelegateAdaptor(AppDelegate.self) var delegate
    @StateObject private var store = AppStore()
    @Environment(\.scenePhase) private var scenePhase

    var body: some Scene {
        WindowGroup {
            Group {
                if store.deletionState != nil || store.deletionRecoveryError != nil {
                    AccountDeletionView(store: store, recovering: true)
                } else if store.user == nil { AuthView() }
                else { MainTabs(store: store) }
            }
            .environmentObject(store)
            .tint(.mint)
            .preferredColorScheme(.dark)
            .alert("Territory Run", isPresented: Binding(get: { store.error != nil }, set: { if !$0 { store.error = nil } })) {
                Button("OK", role: .cancel) { store.error = nil }
            } message: { Text(store.error ?? "") }
            .sheet(item: $store.result) { ResultView(result: $0) }
            .onChange(of: scenePhase) { _, phase in
                if phase == .active { Task { await store.sync() } }
            }
            .onChange(of: store.user?.id) { _, id in
                guard id != nil else { return }
                if let token = UserDefaults.standard.string(forKey: "apnsToken") {
                    Task { await store.registerPushToken(token) }
                }
            }
            .onReceive(NotificationCenter.default.publisher(for: .territoryPushToken)) { notification in
                if let token = notification.object as? String { Task { await store.registerPushToken(token) } }
            }
        }
    }
}

extension Notification.Name {
    static let territoryPushToken = Notification.Name("territoryPushToken")
}

final class AppDelegate: NSObject, UIApplicationDelegate, UNUserNotificationCenterDelegate {
    func application(_ application: UIApplication, didFinishLaunchingWithOptions options: [UIApplication.LaunchOptionsKey: Any]? = nil) -> Bool {
        UNUserNotificationCenter.current().delegate = self
        return true
    }
    func application(_ application: UIApplication, didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data) {
        let token = deviceToken.map { String(format: "%02x", $0) }.joined()
        UserDefaults.standard.set(token, forKey: "apnsToken")
        NotificationCenter.default.post(name: .territoryPushToken, object: token)
    }
    func userNotificationCenter(_ center: UNUserNotificationCenter, willPresent notification: UNNotification,
                                withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void) {
        completionHandler([.banner, .sound, .badge])
    }
}

@MainActor
struct MainTabs: View {
    @ObservedObject var store: AppStore
    var body: some View {
        TabView {
            RunMapView(store: store).tabItem { Label("Run", systemImage: "map.fill") }
            FriendsView().tabItem { Label("Friends", systemImage: "person.2.fill") }
            HistoryView().tabItem { Label("History", systemImage: "clock.arrow.circlepath") }
            ProfileView(store: store).tabItem { Label("You", systemImage: "person.crop.circle") }
        }
        .task {
            while !Task.isCancelled {
                await store.sync()
                do { try await Task.sleep(for: .seconds(30)) } catch { break }
            }
        }
    }
}
