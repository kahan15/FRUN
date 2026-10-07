import SwiftUI

struct PrivacyView: View {
    var body: some View {
        List {
            Section("What is saved") {
                Text("Your account includes your email, username, display name and a securely hashed password. Runs include precise GPS points and times, accuracy, distance, duration, optional step counts, validation results and territory. Friend relationships and your blocked-runner list are saved to control access.")
                Text("The optional pace-check choice is used for validation and is not shown to friends. You can choose Prefer not to say.")
                Text("Weekly goal settings and progress summaries stay in this account's protected storage on this phone. They are not sent to friends or the server and are removed from this phone when account deletion completes.")
            }
            Section("Location and sharing") {
                Text("Location recording starts when you start or resume a run and continues while the screen is locked. Pause or finish stops recording. You can change location and motion permissions in iPhone Settings.")
                Text("Check GPS briefly reads your location accuracy without saving a route. The check stops after 20 seconds or when you leave the running screen or put the app in the background.")
                Text("Only accepted friends can see and capture your territory. Your raw GPS track and step count are not shown to friends. Your username and display name can appear in runner search so people can find you.")
                Text("Runs wait in protected storage on this phone when offline, then upload to the configured service when connectivity allows. During development that service runs on your laptop. Other phones may retain previously downloaded territory while offline.")
            }
            Section("Your controls") {
                Text("Remove or block runners from Friends. Blocking removes the connection, stops new visibility, captures and invitations between the pair, and hides each from the other’s search results. Both keep their independently owned land. Unblocking does not restore friendship. Delete your account from You → Delete account. Deletion requires your password and a server connection. It removes active server data and this phone's saved runs; backup retention and support details belong in the published policy.")
                Text("This version has no advertising or cross-app tracking. It uses Apple's native maps and location services.")
            }
            Section("Policy and support") {
                if let policy = configuredURL("PrivacyPolicyURL") { Link("Privacy policy", destination: policy) }
                if let support = configuredURL("SupportURL") { Link("Contact support", destination: support) }
                #if DEBUG
                Text("Development build: public policy and support pages have not been configured yet. This screen describes the current implementation.")
                    .font(.footnote).foregroundStyle(.secondary)
                #endif
            }
        }.navigationTitle("Privacy and data")
    }

    private func configuredURL(_ key: String) -> URL? {
        guard let value = Bundle.main.object(forInfoDictionaryKey: key) as? String,
              let url = URL(string: value), url.scheme == "https", url.host != nil else { return nil }
        return url
    }
}
