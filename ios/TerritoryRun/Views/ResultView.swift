import SwiftUI

@MainActor
struct ResultView: View {
    let result: RunResult
    @Environment(\.dismiss) private var dismiss
    private var title: String {
        if result.status == "rejected" { return "Run saved for review" }
        if result.fragmentCount == 0 { return "No loop closed" }
        if result.newAreaM2 > 0 { return "New ground. Yours." }
        if result.refreshedAreaM2 > 0 { return "Territory renewed" }
        return "Loop complete"
    }
    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 24) {
                    Image(systemName: result.status == "rejected" ? "exclamationmark.shield.fill" : result.fragmentCount == 0 ? "point.topleft.down.to.point.bottomright.curvepath" : "flag.checkered.circle.fill")
                        .font(.system(size: 64)).foregroundStyle(result.status == "rejected" ? .orange : .mint)
                    Text(title).font(.largeTitle.bold())
                    Text("\(Display.distance(result.distanceM))  ·  \(Display.duration(result.durationS))")
                        .foregroundStyle(.secondary)
                    if result.status == "rejected" {
                        Text("No territory was awarded. The run remains in your history with the checks that failed.")
                        ForEach(result.reasons, id: \.self) { Text(reason($0)).font(.subheadline).foregroundStyle(.secondary) }
                    } else if result.fragmentCount == 0 {
                        Text("Your recorded route did not enclose enough ground to claim. Return close to your starting point, or cross your earlier path to close a loop.")
                        Text("Straight lines and out-and-back runs do not claim territory. Pauses and gaps in GPS coverage are not connected; very small loops are filtered as GPS noise.")
                            .font(.subheadline).foregroundStyle(.secondary)
                    } else {
                        Text(Display.area(result.newAreaM2)).font(.system(size: 44, weight: .bold, design: .rounded)).foregroundStyle(.mint)
                        VStack(spacing: 16) {
                            row("Closed areas", "\(result.fragmentCount)")
                            row("Existing land refreshed", Display.area(result.refreshedAreaM2))
                            row("Taken from friends", Display.area(result.stolenAreaM2))
                            row("Protected ground", Display.area(result.blockedAreaM2))
                        }.padding(18).background(.white.opacity(0.05), in: RoundedRectangle(cornerRadius: 18))
                        if result.blockedAreaM2 > 0 {
                            Text("This portion is protected by an accepted friend’s cooldown, or belongs to a contest created after this run started. Non-friends never block your claim.").font(.caption).foregroundStyle(.secondary)
                        }
                        ForEach(Array(result.steals.enumerated()), id: \.offset) { _, steal in
                            Label("\(Display.area(steal.areaM2)) from @\(steal.victimUsername)", systemImage: "flag.fill").foregroundStyle(.orange)
                        }
                    }
                    if result.status == "flagged" {
                        Label("Awarded, with an activity check flagged for review.", systemImage: "info.circle").font(.caption).foregroundStyle(.secondary)
                    }
                    Button("Back to the map") { dismiss() }
                        .buttonStyle(.borderedProminent).foregroundStyle(.black).frame(maxWidth: .infinity)
                }.padding(24)
            }.toolbar { ToolbarItem(placement: .topBarTrailing) { Button("Done") { dismiss() } } }
        }
    }
    private func row(_ label: String, _ value: String) -> some View {
        HStack { Text(label).foregroundStyle(.secondary); Spacer(); Text(value).bold() }.font(.subheadline)
    }
    private func reason(_ code: String) -> String {
        let reasons = ["insufficient_accurate_fixes": "Too few accurate GPS readings were recorded.",
         "teleport": "A gap between GPS readings covered too much distance.",
         "burst_speed": "A GPS segment exceeded the running speed limit.",
         "pace_ceiling": "Recorded pace exceeded the configured running ceiling.",
         "non_monotonic_timestamps": "GPS timestamps arrived out of order.",
         "future_timestamp": "The phone's clock is ahead of the server.",
         "unsupported_geographic_extent": "The route is outside the supported map extent."]
        return reasons[code] ?? code.replacingOccurrences(of: "_", with: " ").capitalized
    }
}
