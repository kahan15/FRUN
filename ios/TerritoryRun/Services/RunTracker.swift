import Foundation
import Combine
import CoreLocation
import CoreMotion

@MainActor
final class RunTracker: NSObject, ObservableObject, @preconcurrency CLLocationManagerDelegate {
    @Published private(set) var draft: RunDraft?
    @Published private(set) var points: [Fix] = []
    @Published private(set) var recording = false
    @Published private(set) var waitingForPermission = false
    @Published private(set) var distance: Double = 0
    @Published private(set) var accuracy: Double?
    @Published private(set) var gpsSample: Fix?
    @Published private(set) var checkingGPS = false
    @Published private(set) var guidance = LoopGuidance()
    @Published var message: String?
    // Created on the main actor; Core Location delivers delegate calls on this run loop.
    private let manager = CLLocationManager()
    private let pedometer = CMPedometer()
    private var directory: URL?
    private var stepsBeforeSegment = 0
    private var wantsToStart = false
    private var wantsGPSCheck = false
    private var gpsCheckTask: Task<Void, Never>?
    private var needsSegmentBreak = false
    private var sensorGeneration = 0

    override init() {
        super.init()
        manager.delegate = self
        manager.desiredAccuracy = kCLLocationAccuracyBest
        manager.distanceFilter = kCLDistanceFilterNone
        manager.activityType = .fitness
        manager.pausesLocationUpdatesAutomatically = false
    }

    var active: Bool { draft != nil }
    var segments: [[CLLocationCoordinate2D]] {
        var result: [[CLLocationCoordinate2D]] = []
        var previous: Int?
        for point in points {
            if previous != point.segment { result.append([]); previous = point.segment }
            result[result.count - 1].append(point.coordinate)
        }
        return result
    }

    func elapsed(at now: Date) -> Double {
        guard let draft else { return 0 }
        return draft.elapsedBeforeSegment + (draft.resumedAt.map { now.timeIntervalSince($0) } ?? 0)
    }

    func configure(directory: URL) throws {
        guard !recording else { return }
        stopGPSCheck()
        gpsSample = nil; accuracy = nil; guidance = LoopGuidance(); message = nil
        self.directory = nil
        guard let (recovered, recoveredPoints) = try TrackingJournal(directory: directory).recover() else {
            self.directory = directory
            draft = nil; points = []; distance = 0; return
        }
        self.directory = directory
        draft = recovered
        points = recoveredPoints
        distance = zip(points, points.dropFirst()).reduce(0) { total, pair in
            total + (pair.0.segment == pair.1.segment ? location(pair.0).distance(from: location(pair.1)) : 0)
        }
        try saveMetadata()
        message = "Your unfinished run was recovered and paused. Resume it or finish to save."
    }

    private func location(_ fix: Fix) -> CLLocation { CLLocation(latitude: fix.latitude, longitude: fix.longitude) }

    func checkGPS() {
        guard !active, !checkingGPS, !waitingForPermission else { return }
        guard CLLocationManager.locationServicesEnabled() else {
            message = "Enable Location Services in Settings to check GPS."; return
        }
        wantsGPSCheck = true
        switch manager.authorizationStatus {
        case .notDetermined:
            waitingForPermission = true
            manager.requestWhenInUseAuthorization()
        case .authorizedWhenInUse, .authorizedAlways: beginGPSCheck()
        default:
            wantsGPSCheck = false
            message = "Allow location access in Settings to check GPS."
        }
    }

    private func beginGPSCheck() {
        wantsGPSCheck = false
        guard manager.accuracyAuthorization == .fullAccuracy else {
            message = "Turn on Precise Location in Settings, then check GPS again."; return
        }
        checkingGPS = true; gpsSample = nil; message = nil
        manager.startUpdatingLocation()
        gpsCheckTask?.cancel()
        gpsCheckTask = Task { [weak self] in
            do { try await Task.sleep(for: .seconds(20)) } catch { return }
            self?.stopGPSCheck()
        }
    }

    func stopGPSCheck() {
        gpsCheckTask?.cancel(); gpsCheckTask = nil
        if checkingGPS && !recording { manager.stopUpdatingLocation() }
        checkingGPS = false; wantsGPSCheck = false
        if !wantsToStart { waitingForPermission = false }
    }

    func startOrResume() {
        guard !recording, !waitingForPermission else { return }
        stopGPSCheck()
        guard CLLocationManager.locationServicesEnabled() else {
            message = "Enable Location Services in Settings to record a run."
            return
        }
        wantsToStart = true
        switch manager.authorizationStatus {
        case .notDetermined:
            waitingForPermission = true
            manager.requestWhenInUseAuthorization()
        case .authorizedWhenInUse, .authorizedAlways:
            beginRecording()
        default:
            wantsToStart = false
            message = "Allow location access in Settings to record a run."
        }
    }

    func locationManagerDidChangeAuthorization(_ manager: CLLocationManager) {
        switch manager.authorizationStatus {
        case .authorizedAlways, .authorizedWhenInUse:
            waitingForPermission = false
            if recording && manager.accuracyAuthorization != .fullAccuracy {
                pause()
                message = "Tracking paused because Precise Location was turned off. Saved points are preserved."
            } else if wantsToStart { beginRecording() }
            else if wantsGPSCheck { beginGPSCheck() }
        case .denied, .restricted:
            waitingForPermission = false
            wantsToStart = false
            stopGPSCheck(); gpsSample = nil
            if recording { pause() }
            message = "Location permission is off. Your recorded points are still saved."
        default: break
        }
    }

    private func beginRecording() {
        guard !recording else { return }
        guard let directory else {
            wantsToStart = false
            message = "Tracking storage is unavailable. Resolve the saved-file error before starting a run."
            return
        }
        wantsToStart = false
        guard manager.accuracyAuthorization == .fullAccuracy else {
            manager.requestTemporaryFullAccuracyAuthorization(withPurposeKey: "RecordRun")
            message = "Precise Location is needed to validate loops. Enable it, then tap Start or Resume again."
            return
        }
        do {
            if draft == nil {
                draft = RunDraft(clientRunId: UUID(), startedAt: Date(), segment: 0,
                                 steps: nil, elapsedBeforeSegment: 0, resumedAt: nil)
                points = []; distance = 0
                try Data().write(to: directory.appendingPathComponent("active.ndjson"),
                                 options: [.atomic, .completeFileProtectionUntilFirstUserAuthentication])
            }
            draft?.resumedAt = Date()
            try saveMetadata()
            recording = true
            guidance = LoopGuidance()
            needsSegmentBreak = false
            sensorGeneration += 1
            let generation = sensorGeneration
            manager.allowsBackgroundLocationUpdates = true
            manager.showsBackgroundLocationIndicator = true
            manager.startUpdatingLocation()
            if CMPedometer.isStepCountingAvailable() {
                stepsBeforeSegment = draft?.steps ?? 0
                pedometer.startUpdates(from: Date()) { [weak self] data, _ in
                    Task { @MainActor [weak self] in
                        guard let self, self.recording, self.sensorGeneration == generation, let data else { return }
                        self.draft?.steps = self.stepsBeforeSegment + data.numberOfSteps.intValue
                        do { try self.saveMetadata() } catch { self.message = error.localizedDescription }
                    }
                }
            }
            message = nil
        } catch {
            stopSensors()
            draft?.resumedAt = nil
            message = "Could not save tracking data: \(error.localizedDescription)"
        }
    }

    func pause() {
        wantsToStart = false
        waitingForPermission = false
        guard recording else { return }
        stopSensors()
        if let resumed = draft?.resumedAt {
            draft?.elapsedBeforeSegment += Date().timeIntervalSince(resumed)
        }
        draft?.resumedAt = nil
        draft?.segment += 1
        guidance = LoopGuidance(detail: "Paused. Resuming starts a new segment; gaps are never joined.")
        do { try saveMetadata() } catch { message = error.localizedDescription }
    }

    func finish() throws -> RunUpload {
        pause()
        guard let draft else { throw CocoaError(.fileNoSuchFile) }
        return RunUpload(clientRunId: draft.clientRunId, startedAt: draft.startedAt,
                         endedAt: Date(), stepCount: draft.steps, points: points)
    }

    func clearAfterEnqueue() throws {
        guard let directory else { return }
        // Enqueue is already durable. Cleanup failure must never leave a resumable duplicate.
        draft = nil; points = []; distance = 0; accuracy = nil; gpsSample = nil; guidance = LoopGuidance(); message = nil
        try TrackingJournal(directory: directory).clear()
    }

    func discardForAccountDeletion() {
        wantsToStart = false
        waitingForPermission = false
        stopGPSCheck()
        stopSensors()
        draft = nil; points = []; distance = 0; accuracy = nil; gpsSample = nil; guidance = LoopGuidance(); message = nil; directory = nil
    }

    private func stopSensors() {
        recording = false
        sensorGeneration += 1
        manager.stopUpdatingLocation()
        manager.allowsBackgroundLocationUpdates = false
        manager.showsBackgroundLocationIndicator = false
        pedometer.stopUpdates()
    }

    private func saveMetadata() throws {
        guard let draft, let directory else { return }
        try LocalFiles.write(draft, to: directory.appendingPathComponent("active.json"))
    }

    func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        guard recording || checkingGPS else { return }
        if let latest = locations.max(by: { $0.timestamp < $1.timestamp }),
           gpsSample.map({ latest.timestamp >= $0.timestamp }) ?? true {
            gpsSample = Fix(latitude: latest.coordinate.latitude, longitude: latest.coordinate.longitude,
                            timestamp: latest.timestamp, accuracy: latest.horizontalAccuracy, segment: draft?.segment ?? 0)
        }
        guard recording, let directory else { return }
        for location in locations {
            accuracy = location.horizontalAccuracy
            guard let current = draft, let resumedAt = current.resumedAt else { return }
            if points.count >= 60000 { pause(); message = "Tracking limit reached. Finish this run to save it."; return }
            let sample = Fix(latitude: location.coordinate.latitude, longitude: location.coordinate.longitude,
                             timestamp: location.timestamp, accuracy: location.horizontalAccuracy, segment: current.segment)
            var policy = TrackingPolicy(last: points.last, segment: current.segment, needsBreak: needsSegmentBreak)
            let decision = policy.consider(sample, resumedAt: resumedAt, now: Date())
            needsSegmentBreak = policy.needsBreak
            guard case let .accept(segment) = decision else { continue }
            let fix = Fix(latitude: sample.latitude, longitude: sample.longitude, timestamp: sample.timestamp,
                          accuracy: sample.accuracy, segment: segment)
            do {
                try TrackingJournal(directory: directory).append(fix)
                draft?.segment = segment
                if let last = points.last, last.segment == fix.segment {
                    distance += location.distance(from: self.location(last))
                } else if !points.isEmpty {
                    message = "GPS coverage was interrupted. Tracking resumed without connecting the gap."
                }
                points.append(fix)
            } catch {
                pause()
                message = "Tracking paused because the phone could not save GPS data: \(error.localizedDescription)"
                return
            }
        }
        if let segment = draft?.segment { guidance = LoopGuidance.calculate(points, currentSegment: segment) }
    }

    func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {
        needsSegmentBreak = true
        if (error as? CLError)?.code == .denied { pause() }
        message = "Waiting for GPS. Keep the phone with you and move into an open area."
    }
}
