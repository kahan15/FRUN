import SwiftUI
import MapKit

@MainActor
struct RunMapView: View {
    @ObservedObject var store: AppStore
    @ObservedObject var tracker: RunTracker
    @ObservedObject var queue: UploadQueue
    @Environment(\.dynamicTypeSize) private var typeSize
    @Environment(\.scenePhase) private var scenePhase
    @State private var camera: MapCameraPosition = .userLocation(fallback: .automatic)
    @State private var confirmFinish = false
    @State private var centered = false

    init(store: AppStore) {
        self.store = store; self.tracker = store.tracker; self.queue = store.queue
    }

    var body: some View {
        GeometryReader { geometry in
            territoryMap
                .mapStyle(.standard(elevation: .flat))
                .mapControls { MapUserLocationButton(); MapCompass(); MapScaleView() }
                .safeAreaInset(edge: .top) { header.padding(.horizontal, 14).padding(.top, 8) }
                .safeAreaInset(edge: .bottom) {
                    ScrollView { controls.padding(16) }
                        .frame(maxHeight: geometry.size.height * (typeSize.isAccessibilitySize ? 0.70 : 0.56))
                        .fixedSize(horizontal: false, vertical: true)
                        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 24))
                        .padding(12)
                }
        }
        .onChange(of: store.territories.count) { _, _ in
            guard !centered, !tracker.active, let polygon = store.territories.first?.geometry.polygons.first else { return }
            camera = .rect(polygon.boundingMapRect.insetBy(dx: -500, dy: -500)); centered = true
        }
        .onDisappear { tracker.stopGPSCheck() }
        .onChange(of: scenePhase) { _, phase in if phase == .background { tracker.stopGPSCheck() } }
        .sheet(isPresented: $confirmFinish) { finishReview }
    }

    private var header: some View {
        HStack(alignment: .top) {
            VStack(alignment: .leading, spacing: 4) {
                if tracker.active {
                    Label(tracker.recording ? "Recording your run" : "Run paused", systemImage: tracker.recording ? "record.circle" : "pause.circle")
                        .font(.headline).foregroundStyle(.mint)
                } else {
                    Text(Display.area(store.stats.areaM2)).font(.title2.bold().monospacedDigit())
                    Text("Your territory · Friends orange · Contested purple").font(.caption).foregroundStyle(.secondary)
                }
            }
            Spacer(minLength: 8)
            Label(store.connected ? "Synced" : "Offline", systemImage: store.connected ? "checkmark.icloud" : "wifi.slash")
                .font(.caption).foregroundStyle(.secondary)
        }.padding(14).background(.ultraThinMaterial, in: RoundedRectangle(cornerRadius: 20))
    }

    private var territoryMap: some View {
        Map(position: $camera) {
            UserAnnotation()
            territoryOverlays
            contestOverlays
            if !tracker.guidance.preview.isEmpty {
                MapPolygon(coordinates: tracker.guidance.preview)
                    .foregroundStyle(Color.mint.opacity(0.15))
                    .stroke(Color.mint, style: StrokeStyle(lineWidth: 2, dash: [6, 5]))
            }
            routeOverlays
        }
    }

    @MapContentBuilder
    private var territoryOverlays: some MapContent {
        ForEach(store.territories) { feature in
            ForEach(Array(feature.geometry.polygons.enumerated()), id: \.offset) { _, polygon in
                MapPolygon(polygon)
                    .foregroundStyle(feature.properties.ownerId == store.user?.id ? Color.blue.opacity(0.30) : Color.orange.opacity(0.28))
                    .stroke(feature.properties.ownerId == store.user?.id ? Color.blue : Color.orange, lineWidth: 2)
            }
        }
    }

    @MapContentBuilder
    private var contestOverlays: some MapContent {
        ForEach(store.territories) { feature in
            ForEach(Array((feature.properties.contestedGeometry?.polygons ?? []).enumerated()), id: \.offset) { _, polygon in
                MapPolygon(polygon).foregroundStyle(Color.purple.opacity(0.30)).stroke(Color.purple, lineWidth: 3)
            }
        }
    }

    @MapContentBuilder
    private var routeOverlays: some MapContent {
        ForEach(Array(tracker.segments.enumerated()), id: \.offset) { _, coordinates in
            MapPolyline(coordinates: coordinates).stroke(.mint, lineWidth: 5)
        }
    }

    private var controls: some View {
        VStack(alignment: .leading, spacing: 14) {
            if tracker.active {
                TimelineView(.periodic(from: .now, by: 1)) { context in
                    ViewThatFits(in: .horizontal) {
                        HStack(spacing: 24) {
                            metric(Display.distance(tracker.distance), "Distance")
                            metric(Display.duration(tracker.elapsed(at: context.date)), "Active time")
                        }
                        VStack(alignment: .leading, spacing: 10) {
                            metric(Display.distance(tracker.distance), "Distance")
                            metric(Display.duration(tracker.elapsed(at: context.date)), "Active time")
                        }
                    }
                }
                runButtons
                if tracker.recording { gpsStatus }
                if let distance = tracker.guidance.distanceToStart {
                    Label("\(Int(distance.rounded())) m to segment start", systemImage: "arrow.uturn.backward")
                        .font(.subheadline.weight(.semibold))
                        .accessibilityLabel("\(Int(distance.rounded())) metres to the start of this uninterrupted segment")
                }
                if let area = tracker.guidance.estimatedAreaM2 {
                    Text("Estimated loop · \(Display.area(area))").font(.subheadline.weight(.semibold)).foregroundStyle(.mint)
                }
                Text(tracker.guidance.detail).font(.caption).foregroundStyle(.secondary)
            } else {
                WeeklyGoalView(goals: store.goals, compact: true)
                Divider()
                gpsStatus
                Button { tracker.checkGPS() } label: {
                    Label(tracker.checkingGPS ? "Checking GPS…" : "Check GPS", systemImage: "location.circle")
                        .frame(maxWidth: .infinity, minHeight: 44)
                }.buttonStyle(.bordered).disabled(tracker.checkingGPS || tracker.waitingForPermission)
                    .accessibilityHint("Checks your signal for up to 20 seconds without saving a route")
                Button { tracker.startOrResume(); camera = .userLocation(fallback: .automatic) } label: {
                    Label(tracker.waitingForPermission ? "Waiting for permission…" : "Start run", systemImage: "figure.run")
                        .font(.headline).frame(maxWidth: .infinity, minHeight: 60)
                }.buttonStyle(.borderedProminent).foregroundStyle(.black).disabled(tracker.waitingForPermission || store.finishing)
                    .accessibilityIdentifier("startRun")
                Text("Run an uninterrupted loop to capture the ground inside.").font(.caption).foregroundStyle(.secondary)
            }
            if let message = tracker.message {
                Label(message, systemImage: "info.circle").font(.subheadline).foregroundStyle(.orange)
            }
            if !queue.issues.isEmpty {
                Text("\(queue.issues.count) saved run(s) need attention. Files are preserved on this phone.")
                    .font(.caption).foregroundStyle(.orange)
                Button("Retry held uploads") { Task { await store.retryHeldRuns() } }
                    .frame(minHeight: 44).disabled(store.syncing)
            }
            if !queue.pending.isEmpty {
                Button { Task { await store.sync(force: true) } } label: {
                    Label("\(queue.pending.count) saved run(s) · \(store.syncing ? "Syncing…" : "Tap to sync")", systemImage: "arrow.triangle.2.circlepath")
                        .font(.subheadline).frame(minHeight: 44)
                }.disabled(store.syncing)
            }
        }
    }

    private var gpsStatus: some View {
        TimelineView(.periodic(from: .now, by: 1)) { context in
            let state = GPSReadiness.evaluate(tracker.gpsSample, now: context.date)
            VStack(alignment: .leading, spacing: 4) {
                Label(state.title, systemImage: state == .ready ? "location.fill" : "location")
                    .font(.subheadline.weight(.semibold)).foregroundStyle(state == .ready ? Color.mint : .orange)
                if state != .ready {
                    Text(tracker.active ? "Move into an open area. Missing GPS never becomes captured ground." : "Check GPS outdoors before starting for a clearer route.")
                        .font(.caption).foregroundStyle(.secondary)
                }
            }.accessibilityElement(children: .combine)
        }
    }

    private var runButtons: some View {
        ViewThatFits(in: .horizontal) {
            HStack(spacing: 12) { pauseButton; finishButton }
            VStack(spacing: 10) { pauseButton; finishButton }
        }
    }

    private var pauseButton: some View {
        Button { tracker.recording ? tracker.pause() : tracker.startOrResume() } label: {
            Label(tracker.recording ? "Pause" : "Resume", systemImage: tracker.recording ? "pause.fill" : "play.fill")
                .font(.headline).fixedSize().frame(maxWidth: .infinity, minHeight: 60)
        }.buttonStyle(.bordered).disabled(store.finishing)
            .accessibilityHint(tracker.recording ? "Stops recording until you resume. A pause separates loop segments." : "Continues this run in a new GPS segment.")
            .accessibilityIdentifier("pauseResumeRun")
    }

    private var finishButton: some View {
        Button { confirmFinish = true } label: {
            Label("Finish", systemImage: "flag.checkered")
                .font(.headline).fixedSize().frame(maxWidth: .infinity, minHeight: 60)
        }.buttonStyle(.borderedProminent).foregroundStyle(.black).disabled(store.finishing)
            .accessibilityHint("Opens a review. Your run only finishes after you confirm.")
            .accessibilityIdentifier("reviewFinish")
    }

    private var finishReview: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    Text("Ready to finish?").font(.title2.bold())
                    Text("You've recorded \(Display.distance(tracker.distance)). Your route will be saved on this phone, even when offline.")
                    Text(tracker.recording ? "Recording continues until you confirm." : "Your run is paused.")
                        .foregroundStyle(.secondary)
                    Button { confirmFinish = false; Task { await store.finishRun() } } label: {
                        Label("Finish and save run", systemImage: "checkmark.circle.fill")
                            .font(.headline).frame(maxWidth: .infinity, minHeight: 60)
                    }.buttonStyle(.borderedProminent).foregroundStyle(.black).disabled(store.finishing || !tracker.active)
                        .accessibilityIdentifier("confirmFinishRun")
                    Button(tracker.recording ? "Keep running" : "Return to paused run") { confirmFinish = false }
                        .frame(maxWidth: .infinity, minHeight: 52).buttonStyle(.bordered)
                    Text("The server checks your loop and capture eligibility after upload. The map preview is an estimate.")
                        .font(.caption).foregroundStyle(.secondary)
                }.padding(24)
            }.navigationTitle("Review run").navigationBarTitleDisplayMode(.inline)
        }.presentationDetents([.medium, .large]).presentationDragIndicator(.visible)
    }

    private func metric(_ value: String, _ label: String) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(value).font(.title2.bold().monospacedDigit()).fixedSize()
            Text(label).font(.caption).foregroundStyle(.secondary)
        }.accessibilityElement(children: .combine)
    }
}
