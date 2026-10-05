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
    private var gainTree: AUParameterTree!
    public private(set) var lastStateRestoreStatus: Int32 = 0
    public static let privateStateKey = "org.video-utils.gain.state.v1"
    public var gainStateToken: UInt64 { kernel.stateToken }
    public var gainStateRevision: UInt64 { kernel.stateRevision }
    public var gainState: Data? { kernel.copyPrivateState(forToken: kernel.stateToken) }
    public let fullStateSetterQualified = false

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
        let gain = AUParameterTree.createParameter(withIdentifier: "gain", name: "Gain", address: 0,
            min: 0, max: 16, unit: .linearGain, unitName: nil,
            flags: [.flag_IsReadable, .flag_IsWritable, .flag_CanRamp], valueStrings: nil, dependentParameters: nil)
        gain.value = 1
        gainTree = AUParameterTree.createTree(withChildren: [gain])
        gainTree.implementorValueObserver = kernel.gainValueObserver
        gainTree.implementorValueProvider = kernel.gainValueProvider
        parameterTree = gainTree
    }

    public func restoreGainState(_ data: Data, expectedRevision: UInt64, expectedToken: UInt64) throws {
        lastStateRestoreStatus = kernel.restorePrivateState(data, expectedRevision: expectedRevision, expectedToken: expectedToken)
        guard lastStateRestoreStatus == 0 else {
            throw NSError(domain: "video-utils.native-state", code: Int(lastStateRestoreStatus))
        }
        if let gain = gainTree.parameter(withAddress: 0) {
            gain.value = kernel.gainValueProvider(gain)
        }
    }

    public override var fullState: [String: Any]? {
        get {
            let token = kernel.stateToken
            guard var base = super.fullState,
                  let data = kernel.copyPrivateState(forToken: token),
                  let gain = gainTree.parameter(withAddress: 0),
                  gain.value.bitPattern == kernel.gainValueProvider(gain).bitPattern,
                  kernel.stateToken == token else { return nil }
            base[Self.privateStateKey] = data
            return base
        }
        set {
            // Base parameter encoding/transaction remains unqualified; use the
            // checked private helper until its round trip is independently proved.
            if newValue != nil { lastStateRestoreStatus = -100 }
        }
    }

    public override var fullStateForDocument: [String: Any]? {
        get { fullState }
        set { fullState = newValue }
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
