// Out-of-process registered-AU render harness (docs/spec/sprints/AU_AUVAL_S2.md
// section 3; docs/spec/AU_AUVAL_STEP.md). Run only by auval_step.py after
// stage-2 discovery passes. It never constructs GuitarGainAudioUnit directly,
// never installs, registers or repairs anything, and opens no audio device.
//
// Exit codes: 0 all fixtures pass, 1 fixture/instantiation failure,
// 3 blocked (not exactly one matching component), 4 instantiation timeout.
// JSON is printed once, after deallocateRenderResources().

import AVFAudio
import AudioToolbox
import Foundation

func fourCharCode(_ text: String) -> OSType {
    text.utf8.reduce(OSType(0)) { ($0 << 8) | OSType($1) }
}

let targetDescription = AudioComponentDescription(
    componentType: fourCharCode("aufx"),
    componentSubType: fourCharCode("vuGn"),
    componentManufacturer: fourCharCode("Jess"),
    componentFlags: 0,
    componentFlagsMask: 0)

let sampleRate = 48_000.0
let blockSizes = [128, 4096]
let finalBlock = 37
let gains: [Float] = [0, 0.5, 1, 2, 16]
let channelCounts: [AVAudioChannelCount] = [1, 2]
let signalNames = ["impulse", "sine_c1", "lcg_noise"]
let impulsePositions = [5, 77]
let tolerance: Float = 2e-6
let maxFrames = 3 * 4096 + finalBlock

func uptime() -> Double { ProcessInfo.processInfo.systemUptime }

func emit(_ object: [String: Any], exitCode: Int32) -> Never {
    if let data = try? JSONSerialization.data(withJSONObject: object, options: [.sortedKeys]),
       let text = String(data: data, encoding: .utf8) {
        print(text)
    } else {
        print("{\"status\":\"internal_error\",\"reason\":\"json encoding failed\"}")
    }
    exit(exitCode)
}

var report: [String: Any] = [
    "schema": "vu.au_registered_render.v1",
    "component": ["type": "aufx", "subtype": "vuGn", "manufacturer": "Jess"],
    "requested_instantiation_mode": "loadOutOfProcess",
    "observed_instantiation_mode": "unknown",
    "audio_device_opened": false,
    "realtime_deadline": "unknown",
    "timing_scope": "wall-clock categories only; not a realtime deadline measurement",
]

// 1. Exact component enumeration.
let matches = AVAudioUnitComponentManager.shared().components(matching: targetDescription)
report["matching_components"] = matches.count
guard matches.count == 1 else {
    report["status"] = "blocked"
    report["reason"] = matches.isEmpty
        ? "no registered component matches aufx/vuGn/Jess"
        : "ambiguous: \(matches.count) registered components match aufx/vuGn/Jess"
    emit(report, exitCode: 3)
}
report["component_name"] = matches[0].name
report["component_version"] = Int(matches[0].version)
report["component_manufacturer_name"] = matches[0].manufacturerName

// 2. Asynchronous out-of-process instantiation; the main run loop is serviced
// in 50 ms slices up to a 10 s deadline per attempt, at most 3 attempts.
final class InstantiationBox: @unchecked Sendable {
    private let lock = NSLock()
    private var finished = false
    private var unit: AUAudioUnit?
    private var failure: String?

    func finish(_ value: AUAudioUnit?, _ error: (any Error)?) {
        lock.lock()
        finished = true
        unit = value
        failure = error.map { String(describing: $0) }
        lock.unlock()
    }

    func snapshot() -> (Bool, AUAudioUnit?, String?) {
        lock.lock()
        defer { lock.unlock() }
        return (finished, unit, failure)
    }
}

let startupBegan = uptime()
var instantiated: AUAudioUnit?
var attemptLog: [[String: Any]] = []
var timedOut = false
for attempt in 1...3 {
    let box = InstantiationBox()
    AUAudioUnit.instantiate(with: targetDescription, options: [.loadOutOfProcess]) { unit, error in
        box.finish(unit, error)
    }
    let deadline = uptime() + 10
    var state = box.snapshot()
    while !state.0 && uptime() < deadline {
        _ = RunLoop.main.run(mode: .default, before: Date(timeIntervalSinceNow: 0.05))
        state = box.snapshot()
    }
    if let unit = state.1 {
        instantiated = unit
        attemptLog.append(["attempt": attempt, "result": "instantiated"])
        timedOut = false
        break
    }
    timedOut = !state.0
    attemptLog.append(["attempt": attempt, "result": state.0 ? "error" : "timeout",
                       "error": state.2 ?? (state.0 ? "nil unit without error" : "deadline 10 s")])
}
report["instantiation_attempts"] = attemptLog
guard let unit = instantiated else {
    report["status"] = timedOut ? "instantiation_timeout" : "instantiation_failed"
    emit(report, exitCode: timedOut ? 4 : 1)
}
report["observed_instantiation_mode"] = unit.isLoadedInProcess ? "in_process" : "out_of_process"
report["observed_instantiation_source"] = "AUAudioUnit.isLoadedInProcess"
let startupSeconds = uptime() - startupBegan

// 3. Preallocated buffers (control side). Planar channel c lives at
// base + c * maxFrames.
let inputStorage = UnsafeMutablePointer<Float>.allocate(capacity: 2 * maxFrames)
let outputStorage = UnsafeMutablePointer<Float>.allocate(capacity: 2 * maxFrames)
let expectedStorage = UnsafeMutablePointer<Float>.allocate(capacity: 2 * maxFrames)
let outputList = AudioBufferList.allocate(maximumBuffers: 2)
let flagsStorage = UnsafeMutablePointer<AudioUnitRenderActionFlags>.allocate(capacity: 1)
let timestampStorage = UnsafeMutablePointer<AudioTimeStamp>.allocate(capacity: 1)

final class PullContext: @unchecked Sendable {
    let input: UnsafeMutablePointer<Float>
    let stride: Int
    var offset = 0
    init(input: UnsafeMutablePointer<Float>, stride: Int) {
        self.input = input
        self.stride = stride
    }
}

// Built once on the control side. No prints, file I/O or allocation inside
// the returned block.
func makePullInput(_ context: PullContext) -> AURenderPullInputBlock {
    return { _, _, frameCount, _, bufferList in
        let buffers = UnsafeMutableAudioBufferListPointer(bufferList)
        let bytes = Int(frameCount) * MemoryLayout<Float>.size
        for channel in 0..<buffers.count {
            let source = context.input + channel * context.stride + context.offset
            if let destination = buffers[channel].mData {
                destination.copyMemory(from: source, byteCount: bytes)
            } else {
                buffers[channel].mData = UnsafeMutableRawPointer(source)
            }
            buffers[channel].mDataByteSize = UInt32(bytes)
        }
        return noErr
    }
}

let context = PullContext(input: inputStorage, stride: maxFrames)
let pullInput = makePullInput(context)

struct Lcg {
    var state: UInt32
    mutating func unit() -> Float {
        state = state &* 1_664_525 &+ 1_013_904_223
        return Float(Double(state >> 8) / 16_777_216.0 * 2.0 - 1.0)
    }
}

@MainActor
func fill(signal: String, channels: Int, frames: Int, amplitude: Float) {
    var lcg = Lcg(state: 20_261_006)
    for channel in 0..<channels {
        let base = inputStorage + channel * maxFrames
        for n in 0..<frames {
            switch signal {
            case "impulse":
                base[n] = n == impulsePositions[channel] ? amplitude : 0
            case "sine_c1":
                let phase = 2.0 * Double.pi * 32.703 * Double(n) / sampleRate + Double(channel) * Double.pi / 3
                base[n] = amplitude * Float(sin(phase))
            default:
                base[n] = amplitude * lcg.unit()
            }
        }
    }
}

var fixtureTotal = 0
var fixturePassed = 0
var failures: [[String: Any]] = []
var maxAbsoluteError: Float = 0
var processingSeconds = 0.0
var setupFailure: String?

for channels in channelCounts {
    guard let format = AVAudioFormat(standardFormatWithSampleRate: sampleRate, channels: channels) else {
        setupFailure = "format \(channels) channels unavailable"
        break
    }
    for gain in gains {
        do {
            if unit.renderResourcesAllocated { unit.deallocateRenderResources() }
            try unit.inputBusses[0].setFormat(format)
            try unit.outputBusses[0].setFormat(format)
            unit.maximumFramesToRender = 4096
            guard let parameter = unit.parameterTree?.parameter(withAddress: 0) else {
                setupFailure = "gain parameter address 0 not exposed"
                break
            }
            parameter.value = gain
            try unit.allocateRenderResources()
        } catch {
            setupFailure = "setup \(channels)ch gain \(gain): \(error)"
            break
        }
        let render = unit.renderBlock
        for block in blockSizes {
            for signal in signalNames {
                fixtureTotal += 1
                let frames = 3 * block + finalBlock
                // Amplitude 0.01 for gains of 2 or more keeps 16x output bounded.
                let amplitude: Float = gain >= 2 ? 0.01 : (signal == "impulse" ? 1 : signal == "sine_c1" ? 0.5 : 0.25)
                fill(signal: signal, channels: Int(channels), frames: frames, amplitude: amplitude)
                for channel in 0..<Int(channels) {
                    let base = channel * maxFrames
                    for n in 0..<frames {
                        expectedStorage[base + n] = inputStorage[base + n] * gain
                        outputStorage[base + n] = .nan
                    }
                }
                unit.reset()
                var renderStatus: AUAudioUnitStatus = noErr
                let began = uptime()
                var offset = 0
                while offset < frames && renderStatus == noErr {
                    let count = min(block, frames - offset)
                    context.offset = offset
                    let buffers = outputList
                    buffers.count = Int(channels)
                    for channel in 0..<Int(channels) {
                        buffers[channel].mNumberChannels = 1
                        buffers[channel].mDataByteSize = UInt32(count * MemoryLayout<Float>.size)
                        buffers[channel].mData = UnsafeMutableRawPointer(outputStorage + channel * maxFrames + offset)
                    }
                    flagsStorage.pointee = []
                    timestampStorage.pointee = AudioTimeStamp()
                    timestampStorage.pointee.mSampleTime = Double(offset)
                    timestampStorage.pointee.mFlags = .sampleTimeValid
                    renderStatus = render(flagsStorage, timestampStorage, AUAudioFrameCount(count), 0,
                                          outputList.unsafeMutablePointer, pullInput)
                    // A unit may substitute its own buffer; copy back outside the call.
                    for channel in 0..<Int(channels) {
                        let destination = outputStorage + channel * maxFrames + offset
                        if let produced = buffers[channel].mData,
                           produced != UnsafeMutableRawPointer(destination) {
                            destination.update(from: produced.assumingMemoryBound(to: Float.self), count: count)
                        }
                    }
                    offset += count
                }
                processingSeconds += uptime() - began
                var worst: Float = 0
                var offsetErrors = 0
                for channel in 0..<Int(channels) {
                    let base = channel * maxFrames
                    for n in 0..<frames {
                        let error = abs(outputStorage[base + n] - expectedStorage[base + n])
                        worst = error.isNaN ? .infinity : max(worst, error)
                        if signal == "impulse" && gain > 0
                            && (outputStorage[base + n] != 0) != (n == impulsePositions[channel]) {
                            offsetErrors += 1
                        }
                    }
                }
                maxAbsoluteError = max(maxAbsoluteError, worst)
                if renderStatus == noErr && worst <= tolerance && offsetErrors == 0 {
                    fixturePassed += 1
                } else if failures.count < 20 {
                    failures.append(["channels": Int(channels), "gain": Double(gain), "block": block,
                                     "signal": signal, "render_status": Int(renderStatus),
                                     "max_abs_error": Double(worst), "impulse_offset_errors": offsetErrors])
                }
            }
        }
        unit.deallocateRenderResources()
    }
    if setupFailure != nil { break }
}

let teardownBegan = uptime()
if unit.renderResourcesAllocated { unit.deallocateRenderResources() }
inputStorage.deallocate()
outputStorage.deallocate()
expectedStorage.deallocate()
outputList.unsafeMutablePointer.deallocate()
flagsStorage.deallocate()
timestampStorage.deallocate()
let teardownSeconds = uptime() - teardownBegan

let passed = setupFailure == nil && fixtureTotal == 60 && fixturePassed == fixtureTotal
report["status"] = passed ? "passed" : "failed"
report["setup_failure"] = setupFailure ?? NSNull()
report["fixtures"] = ["total": fixtureTotal, "passed": fixturePassed, "expected_total": 60,
                      "matrix": "mono/stereo x gains 0,0.5,1,2,16 x blocks 128,4096 (+final 37) x impulse/sine_c1/lcg_noise at 48 kHz",
                      "oracle": "independent Float32 input*gain", "tolerance_max_abs": Double(tolerance),
                      "impulse_offset_tolerance_samples": 0]
report["failures"] = failures
report["max_abs_error"] = Double(maxAbsoluteError)
report["timing_wall_clock_s"] = ["startup": startupSeconds, "processing": processingSeconds,
                                 "teardown": teardownSeconds]
emit(report, exitCode: passed ? 0 : 1)
