import AudioToolbox
import AVFAudio
import Foundation

func fourCC(_ text: String) -> UInt32 {
    text.utf8.reduce(0) { ($0 << 8) | UInt32($1) }
}

// Direct in-process object construction is not component registration, auval,
// an AUv3 extension load, or a Logic host test. No audio device is opened.
let description = AudioComponentDescription(componentType: fourCC("aufx"),
    componentSubType: fourCC("vuGn"), componentManufacturer: fourCC("Jess"),
    componentFlags: 0, componentFlagsMask: 0)
let unit = try GuitarGainAudioUnit(componentDescription: description)
precondition(unit.inputBusses.count == 1 && unit.outputBusses.count == 1)
try unit.allocateRenderResources()
precondition(unit.renderResourcesAllocated)
unit.deallocateRenderResources()
precondition(!unit.renderResourcesAllocated)
let mono = AVAudioFormat(standardFormatWithSampleRate: 44_100, channels: 1)!
try unit.inputBusses[0].setFormat(mono)
try unit.outputBusses[0].setFormat(mono)
unit.maximumFramesToRender = 128
try unit.allocateRenderResources()
precondition(unit.renderResourcesAllocated)
unit.deallocateRenderResources()
let stereo = AVAudioFormat(standardFormatWithSampleRate: 44_100, channels: 2)!
try unit.outputBusses[0].setFormat(stereo)
do {
    try unit.allocateRenderResources()
    fatalError("mismatched input/output channels were accepted")
} catch {
    precondition(!unit.renderResourcesAllocated)
}
print("{\"swift_au_object_lifecycle\":\"passed\",\"registered_component\":false,\"logic_host_loaded\":false}")
