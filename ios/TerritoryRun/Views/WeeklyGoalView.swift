import SwiftUI

@MainActor
struct WeeklyGoalView: View {
    @ObservedObject var goals: WeeklyGoals
    var compact = false
    @State private var editing = false

    var body: some View {
        TimelineView(.periodic(from: .now, by: 60)) { context in
            let progress = WeeklyProgress.calculate(goals.runs, now: context.date)
            Button { editing = true } label: {
                HStack(spacing: 14) {
                    ZStack {
                        Circle().stroke(Color.secondary.opacity(0.25), lineWidth: 5)
                        Circle().trim(from: 0, to: goals.goal.map { progress.fraction(for: $0) } ?? 0)
                            .stroke(Color.mint, style: StrokeStyle(lineWidth: 5, lineCap: .round))
                            .rotationEffect(.degrees(-90))
                        Image(systemName: goals.goal.map { progress.fraction(for: $0) >= 1 } == true ? "checkmark" : "figure.run")
                            .foregroundStyle(.mint)
                    }.frame(width: compact ? 38 : 52, height: compact ? 38 : 52).accessibilityHidden(true)
                    VStack(alignment: .leading, spacing: 4) {
                        Text("This week's goal").font(compact ? .caption : .headline)
                        if goals.issue != nil { Text("Progress may be incomplete").font(.caption).foregroundStyle(.orange) }
                        if let goal = goals.goal {
                            Text(goal.kind == .distance
                                 ? "\(Display.distance(progress.distanceM)) of \(goal.target) km"
                                 : "\(progress.activeDays) of \(goal.target) active days")
                                .font(.subheadline.weight(.semibold)).monospacedDigit()
                            if !compact {
                                Text(progress.fraction(for: goal) >= 1 ? "Goal reached. Enjoy your next run or rest day." : "Your pace, your week. Rest days are welcome.")
                                    .font(.caption).foregroundStyle(.secondary)
                            }
                        } else {
                            Text("Set a distance or active-days goal").font(.subheadline).foregroundStyle(.secondary)
                        }
                    }
                    Spacer(minLength: 0)
                    Image(systemName: "chevron.right").font(.caption).foregroundStyle(.secondary).accessibilityHidden(true)
                }.padding(.vertical, 6).frame(minHeight: 44).contentShape(Rectangle())
            }.buttonStyle(.plain)
                .accessibilityElement(children: .combine)
                .accessibilityHint("Edit your private weekly goal")
                .accessibilityIdentifier("weeklyGoal")
        }
        .sheet(isPresented: $editing) { WeeklyGoalEditor(goals: goals) }
    }
}

@MainActor
private struct WeeklyGoalEditor: View {
    @ObservedObject var goals: WeeklyGoals
    @Environment(\.dismiss) private var dismiss
    @State private var draft = WeeklyGoal()
    @State private var error: String?

    var body: some View {
        NavigationStack {
            Form {
                Section("Choose your weekly goal") {
                    Picker("Goal", selection: Binding(get: { draft.kind }, set: { kind in
                        draft = WeeklyGoal(kind: kind, target: kind == .distance ? 10 : 3)
                    })) {
                        ForEach(GoalKind.allCases, id: \.self) { Text($0.title).tag($0) }
                    }.pickerStyle(.segmented)
                    Stepper(draft.kind == .distance ? "\(draft.target) km per week" : "\(draft.target) active days per week",
                            value: $draft.target, in: draft.kind == .distance ? 1...200 : 1...7)
                        .accessibilityIdentifier("weeklyGoalTarget")
                }
                Section {
                    Text("Monday–Sunday in your phone's time zone. A day counts after 100 m of saved running. Runs belong to the day they started.")
                    Text("Progress uses completed runs saved on this phone since this feature was added, including offline runs. It is private and separate from territory awards.")
                    Text("Rest days are welcome. Change or turn off your goal anytime.")
                }.font(.subheadline).foregroundStyle(.secondary)
                if let issue = goals.issue { Section { Text(issue).foregroundStyle(.orange) } }
                if goals.goal != nil {
                    Button("Turn off weekly goal") { save(nil) }
                }
            }
            .navigationTitle("Weekly goal").navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
                ToolbarItem(placement: .confirmationAction) { Button("Save") { save(draft) }.fontWeight(.semibold) }
            }
            .onAppear { draft = goals.goal ?? WeeklyGoal() }
            .alert("Goal not saved", isPresented: Binding(get: { error != nil }, set: { if !$0 { error = nil } })) {
                Button("OK", role: .cancel) {}
            } message: { Text(error ?? "") }
        }
    }

    private func save(_ goal: WeeklyGoal?) {
        do { try goals.setGoal(goal); dismiss() }
        catch { self.error = "Could not save the goal. Your previous settings and run files are preserved." }
    }
}
