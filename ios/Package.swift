// swift-tools-version: 5.9
import PackageDescription

// Executes shared persistence, GPS policy, MapKit geometry and API tests on a Mac without Xcode.
// Sensor lifecycle and SwiftUI still require an iPhone/simulator build.
let package = Package(
    name: "TerritoryRunCore",
    platforms: [.macOS(.v14), .iOS(.v17)],
    products: [.library(name: "TerritoryRun", targets: ["TerritoryRun"])],
    targets: [
        .target(name: "TerritoryRun", path: "TerritoryRun",
                exclude: ["App", "Views", "Resources", "Services/RunTracker.swift", "Services/AppStore.swift"],
                sources: ["Models", "Services/LocalFiles.swift", "Services/TrackingJournal.swift",
                          "Services/APIClient.swift", "Services/Keychain.swift", "Services/AccountDeletion.swift"]),
        .testTarget(name: "TerritoryRunTests", dependencies: ["TerritoryRun"], path: "TerritoryRunTests")
    ])
