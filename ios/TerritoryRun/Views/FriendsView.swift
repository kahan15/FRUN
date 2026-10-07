import SwiftUI

@MainActor
struct FriendsView: View {
    @EnvironmentObject private var store: AppStore
    @State private var query = ""
    @State private var results: [Runner] = []
    @State private var searching = false
    @State private var remove: Friend?
    @State private var block: Runner?
    @State private var unblock: Runner?

    var body: some View {
        NavigationStack {
            List {
                Section {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("A little friendly rivalry.").font(.title2.bold())
                        Text("Only accepted friends can see and capture your land. Everyone else can own the same area independently. Accepting a friend makes existing overlaps contested: the first new qualifying run wins the portion captured.")
                            .font(.subheadline).foregroundStyle(.secondary)
                    }.padding(.vertical, 8)
                    HStack {
                        TextField("Find a username", text: $query).textInputAutocapitalization(.never).autocorrectionDisabled()
                        Button { Task { await search() } } label: {
                            if searching { ProgressView() } else { Image(systemName: "magnifyingglass") }
                        }.disabled(query.count < 2 || searching)
                    }
                    ForEach(results) { runner in
                        HStack {
                            VStack(alignment: .leading) { Text(runner.displayName); Text("@\(runner.username)").font(.caption).foregroundStyle(.secondary) }
                            Spacer()
                            if store.friends.contains(where: { $0.id == runner.id }) {
                                Image(systemName: "checkmark").foregroundStyle(.secondary)
                            } else {
                                Button("Add") { Task { await store.friendship("request", id: runner.id) } }.buttonStyle(.bordered)
                            }
                        }.swipeActions {
                            Button("Block", role: .destructive) { block = runner }
                        }
                    }
                }
                let incoming = store.friends.filter { $0.status == "pending" && $0.incoming }
                if !incoming.isEmpty {
                    Section("Incoming requests") {
                        ForEach(incoming) { friend in
                            HStack {
                                Text("@\(friend.username)")
                                Spacer()
                                Button("Accept") { Task { await store.friendship("accept", id: friend.id) } }.buttonStyle(.borderedProminent)
                            }
                        }
                    }
                }
                Section("Your leaderboard") {
                    ForEach(Array(store.rankings.enumerated()), id: \.element.id) { index, runner in
                        HStack(spacing: 14) {
                            Text("\(index + 1)").font(.title3.bold()).foregroundStyle(index == 0 ? .mint : .secondary).frame(width: 24)
                            VStack(alignment: .leading, spacing: 4) {
                                Text(runner.displayName).fontWeight(.semibold)
                                Text(runner.id == store.user?.id ? "You" : "@\(runner.username)").font(.caption).foregroundStyle(.secondary)
                            }
                            Spacer()
                            Text(Display.area(runner.areaM2)).font(.subheadline.monospacedDigit())
                        }.padding(.vertical, 5)
                    }
                    if store.rankings.count <= 1 { Text("Add a friend to get the rivalry started.").font(.caption).foregroundStyle(.secondary) }
                }
                if !store.friends.isEmpty {
                    Section("Connections") {
                        ForEach(store.friends) { friend in
                            HStack {
                                Text("@\(friend.username)")
                                Spacer()
                                Text(friend.status == "accepted" ? "Friends" : friend.incoming ? "Incoming" : "Requested")
                                    .font(.caption).foregroundStyle(.secondary)
                            }.swipeActions {
                                Button("Remove", role: .destructive) { remove = friend }
                                Button("Block", role: .destructive) {
                                    block = Runner(id: friend.id, username: friend.username, displayName: friend.displayName)
                                }
                            }
                        }
                    }
                }
                if !store.blockedRunners.isEmpty {
                    Section("Blocked runners") {
                        ForEach(store.blockedRunners) { runner in
                            HStack {
                                Text("@\(runner.username)")
                                Spacer()
                                Button("Unblock") { unblock = runner }.buttonStyle(.bordered)
                            }
                        }
                    }
                }
            }.navigationTitle("Friends")
                .refreshable { await store.refreshAll() }
                .onSubmit { Task { await search() } }
                .confirmationDialog("Remove this connection?", isPresented: Binding(get: { remove != nil }, set: { if !$0 { remove = nil } })) {
                    Button("Remove connection", role: .destructive) {
                        if let friend = remove { Task { await store.friendship("remove", id: friend.id) } }
                        remove = nil
                    }
                } message: { Text("You will no longer see or capture each other's territory.") }
                .confirmationDialog("Block this runner?", isPresented: Binding(get: { block != nil }, set: { if !$0 { block = nil } })) {
                    Button("Block runner", role: .destructive) {
                        if let runner = block {
                            Task { await store.friendship("block", id: runner.id); results = [] }
                        }
                        block = nil
                    }
                } message: {
                    Text("This removes your connection and stops invitations, search visibility and captures between you. Both runners keep their own land. Previously downloaded information cannot be removed from another offline phone.")
                }
                .confirmationDialog("Unblock this runner?", isPresented: Binding(get: { unblock != nil }, set: { if !$0 { unblock = nil } })) {
                    Button("Unblock runner") {
                        if let runner = unblock { Task { await store.friendship("unblock", id: runner.id) } }
                        unblock = nil
                    }
                } message: { Text("You will need a new accepted friend request to see or capture each other's land again.") }
        }
    }

    private func search() async {
        guard query.count >= 2 else { return }
        searching = true
        defer { searching = false }
        do { results = try await store.search(query) }
        catch is CancellationError { results = [] }
        catch { store.error = error.localizedDescription }
    }
}
