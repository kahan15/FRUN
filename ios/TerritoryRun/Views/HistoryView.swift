import SwiftUI

@MainActor
struct HistoryView: View {
    @EnvironmentObject private var store: AppStore
    var body: some View {
        NavigationStack {
            List {
                if store.history.isEmpty {
                    ContentUnavailableView("Your first loop awaits", systemImage: "figure.run",
                        description: Text("Completed runs appear here after they sync with your laptop."))
                }
                ForEach(store.history) { run in
                    Button { store.result = run } label: {
                        VStack(alignment: .leading, spacing: 12) {
                            HStack {
                                Text(run.createdAt.formatted(date: .abbreviated, time: .shortened)).font(.subheadline).foregroundStyle(.secondary)
                                Spacer()
                                Text(run.status.capitalized).font(.caption2.bold())
                                    .padding(.horizontal, 8).padding(.vertical, 4)
                                    .background((run.status == "rejected" ? Color.orange : Color.mint).opacity(0.15), in: Capsule())
                            }
                            HStack {
                                Text(Display.distance(run.distanceM)).font(.title3.bold())
                                Spacer()
                                Text("+\(Display.area(run.newAreaM2))").foregroundStyle(.mint)
                            }
                            Text("\(Display.duration(run.durationS)) · \(run.fragmentCount) closed area(s)").font(.caption).foregroundStyle(.secondary)
                        }.padding(.vertical, 8)
                    }.foregroundStyle(.primary)
                }
                if store.historyHasMore && !store.history.isEmpty {
                    Button("Load older runs") { Task { await store.moreHistory() } }
                }
            }.navigationTitle("Your runs").refreshable { await store.refreshAll() }
        }
    }
}
