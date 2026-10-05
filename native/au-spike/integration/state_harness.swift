import AudioToolbox
import AVFAudio
import Foundation

// Harness-only transfer of the direct object. Production callbacks use native
// atomics; this fixture does not claim arbitrary host threading or TSAN proof.
private final class GetterFixture: @unchecked Sendable {
    let unit: GuitarGainAudioUnit
    let parameter: AUParameter
    var available = 0
    var unavailable = 0
    init(_ unit: GuitarGainAudioUnit, _ parameter: AUParameter) { self.unit = unit; self.parameter = parameter }
}

@main struct StateHarness {
    static func fourCC(_ text: String) -> UInt32 { text.utf8.reduce(0) { ($0 << 8) | UInt32($1) } }
    static func gain(_ data: Data) -> Float {
        precondition(data.count == 32)
        let bits = (0..<4).reduce(UInt32(0)) { $0 | UInt32(data[24+$1]) << UInt32(8*$1) }
        return Float(bitPattern: bits)
    }
    static func near(_ a: Float, _ b: Float) { precondition(abs(a-b) < 0.000002) }
    static func main() throws {
        let description = AudioComponentDescription(componentType: fourCC("aufx"),
            componentSubType: fourCC("vuGn"), componentManufacturer: fourCC("Jess"), componentFlags: 0, componentFlagsMask: 0)
        let unit = try GuitarGainAudioUnit(componentDescription: description)
        let tree = unit.parameterTree!
        precondition(tree.allParameters.count == 1)
        let parameter = tree.parameter(withAddress: 0)!
        precondition(parameter.identifier == "gain" && parameter.minValue == 0 && parameter.maxValue == 16)
        precondition(parameter.flags.contains([.flag_IsReadable, .flag_IsWritable, .flag_CanRamp]))
        near(parameter.value,1)
        parameter.value = 0.25
        let quarter = unit.gainState!
        near(gain(quarter),0.25)
        parameter.value = 0.5
        let half = unit.gainState!
        try unit.restoreGainState(quarter, expectedRevision: unit.gainStateRevision, expectedToken: unit.gainStateToken)
        near(parameter.value,0.25)
        let state = unit.fullState!
        near(gain(state[GuitarGainAudioUnit.privateStateKey] as! Data),0.25)
        precondition((unit.fullStateForDocument![GuitarGainAudioUnit.privateStateKey] as! Data) == quarter)
        let originalToken = unit.gainStateToken
        let originalRevision = unit.gainStateRevision
        unit.fullState = state // Deliberately unqualified setter must preserve state.
        precondition(unit.lastStateRestoreStatus == -100 && unit.gainStateToken == originalToken)
        unit.fullState = nil
        precondition(unit.gainStateToken == originalToken)
        var incompatible = quarter; incompatible[4] = 2
        do { try unit.restoreGainState(incompatible, expectedRevision: originalRevision, expectedToken: originalToken)
             preconditionFailure("incompatible state accepted") } catch {}
        precondition(unit.gainStateToken == originalToken && unit.gainStateRevision == originalRevision)
        do { try unit.restoreGainState(half, expectedRevision: originalRevision+1, expectedToken: originalToken)
             preconditionFailure("stale revision accepted") } catch {}
        let mono = AVAudioFormat(standardFormatWithSampleRate: 48_000, channels: 1)!
        try unit.inputBusses[0].setFormat(mono); try unit.outputBusses[0].setFormat(mono)
        unit.maximumFramesToRender = 128
        let render = unit.renderBlock
        let schedule = unit.scheduleParameterBlock
        try unit.allocateRenderResources()
        precondition(unit.parameterTree === tree)
        do { try unit.restoreGainState(half, expectedRevision: originalRevision, expectedToken: originalToken)
             preconditionFailure("active restore accepted") } catch {}
        let outputStorage = UnsafeMutablePointer<AudioBufferList>.allocate(capacity: 1)
        outputStorage.initialize(to: AudioBufferList())
        outputStorage.pointee.mNumberBuffers = 1
        let output = UnsafeMutableAudioBufferListPointer(outputStorage)
        defer { outputStorage.deinitialize(count: 1); outputStorage.deallocate() }
        var samples = [Float](repeating: 0, count: 128)
        var stamp = AudioTimeStamp(); stamp.mFlags = .sampleTimeValid; stamp.mSampleTime = 0
        var flags = AudioUnitRenderActionFlags()
        let pull: AURenderPullInputBlock = { _, _, count, _, list in
            let buffers = UnsafeMutableAudioBufferListPointer(list)
            for buffer in buffers {
                let p = buffer.mData!.assumingMemoryBound(to: Float.self)
                for i in 0..<Int(count) { p[i] = 1 }
            }
            return noErr
        }
        func process(_ time: Double) {
            stamp.mSampleTime = time
            samples.withUnsafeMutableBytes { bytes in
                output[0] = AudioBuffer(mNumberChannels: 1, mDataByteSize: UInt32(bytes.count), mData: bytes.baseAddress)
                precondition(render(&flags, &stamp, 128, 0, output.unsafeMutablePointer, pull) == noErr)
            }
        }
        process(0); near(samples[0],0.25); near(samples[127],0.25)
        schedule(130,0,0,1)
        process(128); near(samples[0],0.25); near(samples[1],0.25); near(samples[2],1)
        schedule(256,256,0,0)
        process(256); near(samples[0],1); near(samples[127],129/256)
        process(384); near(samples[0],0.5); near(samples[127],1/256)
        process(512); near(samples[0],0)
        parameter.value = 1
        process(640); near(samples[0],0); near(samples[32],0.5); near(samples[64],1)
        // Actual AUParameter publication may clamp; native ingress rejects invalids.
        parameter.value = 17
        let appleClamped = parameter.value
        precondition(appleClamped >= 0 && appleClamped <= 16)
        parameter.value = 1
        var availableGetters = 0
        for _ in 0..<100 {
            if let current = unit.fullState {
                let privateGain = gain(current[GuitarGainAudioUnit.privateStateKey] as! Data)
                near(privateGain,parameter.value); availableGetters += 1
            }
        }
        let getterFixture = GetterFixture(unit,parameter)
        let getterGroup = DispatchGroup()
        DispatchQueue.global().async(group: getterGroup) {
            for i in 0..<1000 {
                getterFixture.parameter.value = Float(i%17)/16
                if let current = getterFixture.unit.fullState {
                    let value = gain(current[GuitarGainAudioUnit.privateStateKey] as! Data)
                    precondition(value.isFinite && value >= 0 && value <= 16)
                    getterFixture.available += 1
                } else { getterFixture.unavailable += 1 }
            }
        }
        for i in 0..<500 {
            let time = 768+i*128
            schedule(AUEventSampleTime(time+2),0,0,Float(i%9)/8)
            process(Double(time))
        }
        precondition(getterGroup.wait(timeout: .now()+10) == .success)
        precondition(getterFixture.available+getterFixture.unavailable == 1000)
        unit.deallocateRenderResources()
        try unit.restoreGainState(half, expectedRevision: unit.gainStateRevision, expectedToken: unit.gainStateToken)
        near(parameter.value,0.5)
        try unit.allocateRenderResources(); process(0); near(samples[0],0.5)
        unit.deallocateRenderResources()
        let shape = state.mapValues { value -> String in
            if let data = value as? Data { return "Data(\(data.count))" }
            if let array = value as? [Any] { return "Array(\(array.count))" }
            if let dictionary = value as? [String: Any] { return "Dictionary(\(dictionary.keys.sorted().joined(separator: ",")))" }
            return String(describing: type(of: value))
        }
        let receipt: [String: Any] = ["status": "passed", "direct_au_object": true,
            "base_schedule_frame_test": true, "checked_private_restore": true,
            "fullState_setter_qualified": unit.fullStateSetterQualified,
            "available_state_getters": availableGetters, "apple_parameter_17_result": appleClamped,
            "concurrent_available_state_getters": getterFixture.available,
            "concurrent_unavailable_state_getters": getterFixture.unavailable,
            "superclass_dictionary_shape": shape, "registered_component": false,
            "auval": "not_performed", "logic_host_loaded": false, "audio_device_opened": false]
        print(String(decoding: try JSONSerialization.data(withJSONObject: receipt, options: .sortedKeys), as: UTF8.self))
    }
}
