#import "GainKernel.h"
#include <atomic>
#include <cassert>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <new>

// Count native C++ allocations during the callback, not preparation.
static std::atomic<bool> trackNew{false};
static std::atomic<size_t> newCalls{0};
void *operator new(size_t size) {
    if (trackNew.load(std::memory_order_relaxed)) newCalls.fetch_add(1, std::memory_order_relaxed);
    if (void *pointer = std::malloc(size ? size : 1)) return pointer;
    throw std::bad_alloc();
}
void operator delete(void *pointer) noexcept { std::free(pointer); }
void operator delete(void *pointer, size_t) noexcept { std::free(pointer); }

struct StereoList { UInt32 mNumberBuffers; AudioBuffer mBuffers[2]; };
static bool invalidInput = false;

int main() {
    @autoreleasepool {
        VUGainKernel *kernel = [[VUGainKernel alloc] init];
        AUInternalRenderBlock block = kernel.renderBlock;
        AudioTimeStamp timestamp{};
        timestamp.mFlags = kAudioTimeStampSampleTimeValid;
        AudioUnitRenderActionFlags flags = 0;
        float left[64], right[64];
        for (auto &sample : left) sample = -999;
        for (auto &sample : right) sample = -999;
        StereoList output{2, {{1, sizeof(left), left}, {1, sizeof(right), right}}};
        auto *abl = reinterpret_cast<AudioBufferList *>(&output);
        AURenderPullInputBlock pull = ^AUAudioUnitStatus(AudioUnitRenderActionFlags *,
            const AudioTimeStamp *, AUAudioFrameCount count, NSInteger, AudioBufferList *input) {
            for (uint32_t channel = 0; channel < input->mNumberBuffers; ++channel) {
                auto *samples = static_cast<float *>(input->mBuffers[channel].mData);
                for (uint32_t index = 0; index < count; ++index) samples[index] = (channel ? -.25f : .25f);
            }
            if (invalidInput && count) static_cast<float *>(input->mBuffers[1].mData)[count-1] = INFINITY;
            return noErr;
        };
        assert(block(&flags, &timestamp, 64, 0, abl, nullptr, pull) == kAudioUnitErr_Uninitialized);
        assert(![kernel prepareWithMaximumFrames:0 channels:2]);
        assert(![kernel prepareWithMaximumFrames:4097 channels:2]);
        assert(![kernel prepareWithMaximumFrames:64 channels:3]);
        assert(![kernel setLinearGain:NAN]);
        assert([kernel setLinearGain:2]);
        assert([kernel prepareWithMaximumFrames:64 channels:2]);
        newCalls.store(0);
        trackNew.store(true);
        OSStatus status = noErr;
        for (uint32_t iteration = 0; iteration < 1024; ++iteration)
            status |= block(&flags, &timestamp, 64, 0, abl, nullptr, pull);
        trackNew.store(false);
        assert(status == noErr && newCalls.load() == 0);
        for (auto sample : left) assert(sample == .5f);
        for (auto sample : right) assert(sample == -.5f);

        assert(block(&flags, &timestamp, 65, 0, abl, nullptr, pull) == kAudioUnitErr_TooManyFramesToProcess);
        assert(block(&flags, &timestamp, 64, 1, abl, nullptr, pull) == kAudio_ParamError);
        assert(block(nullptr, &timestamp, 64, 0, abl, nullptr, pull) == kAudio_ParamError);
        assert(block(&flags, &timestamp, 64, 0, abl, nullptr, nil) == kAudio_ParamError);
        AURenderEvent event{};
        assert(block(&flags, &timestamp, 64, 0, abl, &event, pull) == kAudio_ParamError);
        output.mBuffers[0].mDataByteSize = sizeof(float);
        assert(block(&flags, &timestamp, 64, 0, abl, nullptr, pull) == kAudio_ParamError);
        output.mBuffers[0].mDataByteSize = sizeof(left);
        output.mBuffers[0].mNumberChannels = 2;
        assert(block(&flags, &timestamp, 64, 0, abl, nullptr, pull) == kAudioUnitErr_FormatNotSupported);
        output.mBuffers[0].mNumberChannels = 1;
        invalidInput = true;
        for (auto &sample : left) sample = -999;
        for (auto &sample : right) sample = -999;
        assert(block(&flags, &timestamp, 64, 0, abl, nullptr, pull) == kAudio_ParamError);
        for (auto sample : left) assert(sample == -999);
        for (auto sample : right) assert(sample == -999);
        invalidInput = false;
        output.mBuffers[0].mData = nullptr;
        output.mBuffers[1].mData = nullptr;
        assert(block(&flags, &timestamp, 64, 0, abl, nullptr, pull) == noErr);
        assert(static_cast<float *>(output.mBuffers[0].mData)[0] == .5f);
        assert(static_cast<float *>(output.mBuffers[1].mData)[0] == -.5f);
        [kernel releaseResources];
        assert(block(&flags, &timestamp, 64, 0, abl, nullptr, pull) == kAudioUnitErr_Uninitialized);
        kernel = nil;
        assert(block(&flags, &timestamp, 64, 0, abl, nullptr, pull) == kAudioUnitErr_Uninitialized);
        std::puts("{\"native_kernel\":\"passed\",\"render_iterations\":1024,\"cpp_new_calls_in_render\":0}");
    }
    return 0;
}
