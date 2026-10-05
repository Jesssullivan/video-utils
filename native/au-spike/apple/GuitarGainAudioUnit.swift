import AudioToolbox
import AVFAudio
import Foundation

/// Native-source scaffold. No extension bundle, registration or Logic proof.
@objc(GuitarGainAudioUnit)
public final class GuitarGainAudioUnit: AUAudioUnit {
    private let kernel = VUGainKernel()
    private var inputBus: AUAudioUnitBus!
    private var outputBus: AUAudioUnitBus!
    private var inputBusArray: AUAudioUnitBusArray!
    private var outputBusArray: AUAudioUnitBusArray!

    public override init(componentDescription: AudioComponentDescription,
                         options: AudioComponentInstantiationOptions = []) throws {
        try super.init(componentDescription: componentDescription, options: options)
        guard let format = AVAudioFormat(standardFormatWithSampleRate: 48_000, channels: 2) else {
            throw Self.formatError()
        }
        inputBus = try AUAudioUnitBus(format: format)
        outputBus = try AUAudioUnitBus(format: format)
        inputBusArray = AUAudioUnitBusArray(audioUnit: self, busType: .input, busses: [inputBus])
        outputBusArray = AUAudioUnitBusArray(audioUnit: self, busType: .output, busses: [outputBus])
        maximumFramesToRender = 4096
    }

    public override var inputBusses: AUAudioUnitBusArray { inputBusArray }
    public override var outputBusses: AUAudioUnitBusArray { outputBusArray }
    public override var latency: TimeInterval { 0 }

    public override func allocateRenderResources() throws {
        let input = inputBus.format
        let output = outputBus.format
        guard input.commonFormat == .pcmFormatFloat32,
              output.commonFormat == .pcmFormatFloat32,
              !input.isInterleaved, !output.isInterleaved,
              input.channelCount == output.channelCount,
              (1...2).contains(input.channelCount),
              input.sampleRate == output.sampleRate,
              (8_000...384_000).contains(input.sampleRate),
              (1...4096).contains(maximumFramesToRender) else {
            throw Self.formatError()
        }
        try super.allocateRenderResources()
        guard kernel.prepare(withMaximumFrames: maximumFramesToRender,
                             channels: input.channelCount) else {
            super.deallocateRenderResources()
            throw Self.formatError()
        }
    }

    public override func deallocateRenderResources() {
        kernel.releaseResources()
        super.deallocateRenderResources()
    }

    public override var internalRenderBlock: AUInternalRenderBlock { kernel.renderBlock }

    private static func formatError() -> NSError {
        NSError(domain: NSOSStatusErrorDomain,
                code: Int(kAudioUnitErr_FormatNotSupported),
                userInfo: [NSLocalizedDescriptionKey:
                    "Gain spike requires matching mono/stereo planar Float32 and at most 4096 frames."])
    }
}
