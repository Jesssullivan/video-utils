import AudioToolbox
import Foundation

/// No-UI AUv3 principal class. This source is compiled, never loaded by the check.
@objc(VideoUtilsGainFactory)
public final class VideoUtilsGainFactory: NSObject, AUAudioUnitFactory {
    public func beginRequest(with context: NSExtensionContext) {}

    public func createAudioUnit(with description: AudioComponentDescription) throws -> AUAudioUnit {
        guard description.componentType == 0x61756678,       // aufx
              description.componentSubType == 0x7675476e,    // vuGn
              description.componentManufacturer == 0x4a657373 else { // Jess
            throw NSError(domain: "video-utils.packaging", code: -1,
                          userInfo: [NSLocalizedDescriptionKey: "Unsupported component identity"])
        }
        return try GuitarGainAudioUnit(componentDescription: description)
    }
}
