import SwiftUI

@MainActor
struct AuthView: View {
    @EnvironmentObject private var store: AppStore
    @State private var registering = false
    @State private var username = ""
    @State private var email = ""
    @State private var password = ""
    @State private var displayName = ""
    @State private var sex = "X"
    @State private var server = ""
    @State private var busy = false
    @State private var recovering = false

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 26) {
                    Image(systemName: "figure.run.circle.fill")
                        .font(.system(size: 72)).foregroundStyle(.mint)
                        .padding(.top, 20)
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Your run.\nYour ground.").font(.system(size: 42, weight: .bold, design: .rounded))
                        Text("Close a loop. Claim your neighbourhood.\nKeep it between friends.")
                            .font(.body).foregroundStyle(.secondary)
                    }
                    Picker("Account", selection: $registering) {
                        Text("Sign in").tag(false)
                        Text("Create account").tag(true)
                    }.pickerStyle(.segmented)
                    VStack(spacing: 14) {
                        field("Username", text: $username).textContentType(.username)
                        if registering {
                            field("Email", text: $email).keyboardType(.emailAddress).textContentType(.emailAddress)
                            field("Display name", text: $displayName).textContentType(.name)
                        }
                        SecureField(registering ? "Password · at least 10 characters" : "Password", text: $password)
                            .textContentType(registering ? .newPassword : .password)
                            .padding(16).background(.white.opacity(0.06), in: RoundedRectangle(cornerRadius: 14))
                    }
                    if registering {
                        VStack(alignment: .leading, spacing: 10) {
                            Text("Pace check · optional").font(.subheadline.bold())
                            Picker("Pace ceiling", selection: $sex) {
                                Text("Prefer not to say").tag("X")
                                Text("Male").tag("M")
                                Text("Female").tag("F")
                            }.pickerStyle(.menu)
                            Text("Used only for the running pace check. Never shown on your profile or shared with friends. Prefer not to say uses the more permissive ceiling.")
                                .font(.caption).foregroundStyle(.secondary)
                        }
                    }
                    #if DEBUG
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Laptop server").font(.subheadline.bold())
                        field("http://192.168.1.20:8000", text: $server).keyboardType(.URL)
                        Text("Use the address shown by the laptop setup script. Connect both devices to the same trusted Wi-Fi for sync.")
                            .font(.caption).foregroundStyle(.secondary)
                    }
                    #endif
                    Button {
                        busy = true
                        Task {
                            await store.authenticate(register: registering, username: username.trimmingCharacters(in: .whitespaces),
                                email: email, password: password, displayName: displayName, sex: sex, server: server)
                            busy = false
                        }
                    } label: {
                        HStack {
                            Spacer()
                            if busy { ProgressView().tint(.black) }
                            else { Text(registering ? "Create your runner" : "Let's run").fontWeight(.bold) }
                            Spacer()
                        }.padding(18)
                    }
                    .buttonStyle(.borderedProminent).foregroundStyle(.black)
                    .disabled(busy || username.isEmpty || password.isEmpty || (registering && (email.isEmpty || displayName.isEmpty || password.count < 10)))
                    if !registering {
                        Button("Forgot password?") { recovering = true }.disabled(busy)
                    }
                    NavigationLink("Privacy and data") { PrivacyView() }
                    Text("Recorded runs stay on your phone until they sync to the server.")
                        .font(.caption).foregroundStyle(.secondary)
                }.padding(24)
            }.background(Color(red: 0.035, green: 0.065, blue: 0.075))
                .onAppear { server = store.api.server }
                .sheet(isPresented: $recovering) { PasswordRecoveryView(server: server) }
        }
    }

    private func field(_ label: String, text: Binding<String>) -> some View {
        TextField(label, text: text).textInputAutocapitalization(.never).autocorrectionDisabled()
            .padding(16).background(.white.opacity(0.06), in: RoundedRectangle(cornerRadius: 14))
    }
}
