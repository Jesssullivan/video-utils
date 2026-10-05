#import "GainKernel.h"
#include "video_utils_gain.h"
#include <array>
#include <atomic>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <memory>

namespace {
constexpr uint32_t kMaximumFrames = 4096;
constexpr uint32_t kMaximumChannels = 2;
static_assert(std::atomic<uint32_t>::is_always_lock_free);
static_assert(std::atomic<bool>::is_always_lock_free);

uint32_t gainBits(float value) {
    uint32_t bits;
    std::memcpy(&bits, &value, sizeof(bits));
    return bits;
}

struct KernelState {
    std::atomic<bool> prepared{false};
    std::atomic<uint32_t> gain{gainBits(1.0f)};
    uint32_t maximumFrames = 0;
    uint32_t channels = 0;
    std::array<float, kMaximumFrames * kMaximumChannels> scratch{};
};

struct StereoBufferList {
    UInt32 mNumberBuffers;
    AudioBuffer mBuffers[kMaximumChannels];
};
static_assert(offsetof(StereoBufferList, mBuffers) == offsetof(AudioBufferList, mBuffers));

OSStatus render(KernelState &state, AudioUnitRenderActionFlags *flags,
                const AudioTimeStamp *timestamp, AUAudioFrameCount frames,
                NSInteger bus, AudioBufferList *output, const AURenderEvent *events,
                __unsafe_unretained AURenderPullInputBlock pullInput) {
    if (!state.prepared.load(std::memory_order_acquire)) return kAudioUnitErr_Uninitialized;
    if (!flags || !timestamp || !output || !pullInput || bus != 0 || events) return kAudio_ParamError;
    if (frames > state.maximumFrames) return kAudioUnitErr_TooManyFramesToProcess;
    if (output->mNumberBuffers != state.channels) return kAudioUnitErr_FormatNotSupported;
    const uint32_t bytes = frames * sizeof(float);
    for (uint32_t channel = 0; channel < state.channels; ++channel) {
        const auto &buffer = output->mBuffers[channel];
        if (buffer.mNumberChannels != 1) return kAudioUnitErr_FormatNotSupported;
        if (buffer.mData && buffer.mDataByteSize < bytes) return kAudio_ParamError;
    }
    if (frames == 0) return noErr;

    // Stack metadata and prepared scratch only; no allocation or ObjC message.
    StereoBufferList input{};
    input.mNumberBuffers = state.channels;
    for (uint32_t channel = 0; channel < state.channels; ++channel) {
        input.mBuffers[channel] = {1, bytes, state.scratch.data() + channel * frames};
    }
    const auto pulled = pullInput(flags, timestamp, frames, 0,
                                  reinterpret_cast<AudioBufferList *>(&input));
    if (pulled != noErr) return pulled;
    if (input.mNumberBuffers != state.channels) return kAudioUnitErr_FormatNotSupported;
    for (uint32_t channel = 0; channel < state.channels; ++channel) {
        const auto &buffer = input.mBuffers[channel];
        if (buffer.mNumberChannels != 1 || !buffer.mData || buffer.mDataByteSize < bytes)
            return kAudio_ParamError;
        auto *target = state.scratch.data() + channel * frames;
        if (buffer.mData != target) std::memmove(target, buffer.mData, bytes);
    }
    auto bits = state.gain.load(std::memory_order_relaxed);
    float gain;
    std::memcpy(&gain, &bits, sizeof(gain));
    if (vu_gain_process(state.scratch.data(), frames * state.channels, gain) != VU_OK)
        return kAudio_ParamError;
    for (uint32_t channel = 0; channel < state.channels; ++channel) {
        auto &buffer = output->mBuffers[channel];
        auto *processed = state.scratch.data() + channel * frames;
        if (buffer.mData) std::memmove(buffer.mData, processed, bytes);
        else buffer.mData = processed;
        buffer.mDataByteSize = bytes;
    }
    return noErr;
}
} // namespace

@implementation VUGainKernel {
    std::shared_ptr<KernelState> _state;
}

- (instancetype)init {
    self = [super init];
    if (self) _state = std::make_shared<KernelState>();
    return self;
}

- (BOOL)prepareWithMaximumFrames:(uint32_t)frames channels:(uint32_t)channels {
    if (!frames || frames > kMaximumFrames || !channels || channels > kMaximumChannels
        || vu_gain_abi_version() != 1 || vu_gain_max_samples() < frames * channels)
        return NO;
    // The host must quiesce rendering before reconfiguration/deallocation.
    _state->prepared.store(false, std::memory_order_release);
    _state->maximumFrames = frames;
    _state->channels = channels;
    _state->prepared.store(true, std::memory_order_release);
    return YES;
}

- (void)releaseResources { _state->prepared.store(false, std::memory_order_release); }

- (BOOL)setLinearGain:(float)gain {
    if (!std::isfinite(gain) || gain < 0 || gain > 16) return NO;
    _state->gain.store(gainBits(gain), std::memory_order_relaxed);
    return YES;
}

- (AUInternalRenderBlock)renderBlock {
    // Capture ownership outside rendering; cached blocks cannot dangle after
    // kernel destruction. The invocation body contains only native operations.
    auto state = _state;
    return ^AUAudioUnitStatus(AudioUnitRenderActionFlags *flags,
                             const AudioTimeStamp *timestamp, AUAudioFrameCount frames,
                             NSInteger bus, AudioBufferList *output,
                             const AURenderEvent *events,
                             __unsafe_unretained AURenderPullInputBlock pullInput) {
        return render(*state, flags, timestamp, frames, bus, output, events, pullInput);
    };
}

- (void)dealloc { _state->prepared.store(false, std::memory_order_release); }
@end
