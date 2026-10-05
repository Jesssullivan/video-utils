#import "GainKernel.h"
#include "video_utils_gain.h"
#include "../state/ParameterState.hpp"
#include "../automation/AppleEvents.hpp"
#include "../integration/ControlIngress.hpp"
#include <array>
#include <atomic>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <memory>

namespace {
constexpr uint32_t kMaximumFrames = 4096, kMaximumChannels = 2;
static_assert(std::atomic<bool>::is_always_lock_free);
struct KernelState {
    std::atomic<bool> prepared{false};
    vui::ControlIngress ingress;
    vus::Session session;
    uint64_t published = 0;
    uint32_t maximumFrames = 0, channels = 0;
    std::array<float,kMaximumFrames*kMaximumChannels> inputPlanes{}, planes{}, interleaved{};
};
struct StereoBufferList { UInt32 mNumberBuffers; AudioBuffer mBuffers[kMaximumChannels]; };
static_assert(offsetof(StereoBufferList,mBuffers)==offsetof(AudioBufferList,mBuffers));

OSStatus render(KernelState& state, AudioUnitRenderActionFlags* flags,
                const AudioTimeStamp* timestamp, AUAudioFrameCount frames,
                NSInteger bus, AudioBufferList* output, const AURenderEvent* events,
                __unsafe_unretained AURenderPullInputBlock pullInput) {
    if (!state.prepared.load(std::memory_order_acquire)) return kAudioUnitErr_Uninitialized;
    if (!flags || !timestamp || !output || !pullInput || bus != 0) return kAudio_ParamError;
    if (frames > state.maximumFrames) return kAudioUnitErr_TooManyFramesToProcess;
    if (output->mNumberBuffers != state.channels) return kAudioUnitErr_FormatNotSupported;
    const uint32_t bytes = frames*sizeof(float);
    for (uint32_t channel=0;channel<state.channels;++channel) {
        const auto& buffer=output->mBuffers[channel];
        if (buffer.mNumberChannels != 1) return kAudioUnitErr_FormatNotSupported;
        if (buffer.mData && buffer.mDataByteSize < bytes) return kAudio_ParamError;
    }
    vu::Batch batch;
    if (events) {
        const double time=timestamp->mSampleTime;
        if (!(timestamp->mFlags & kAudioTimeStampSampleTimeValid) || !std::isfinite(time)
            || time < -9223372036854775808.0 || time >= 9223372036854775808.0 || std::trunc(time)!=time)
            return kAudio_ParamError;
        if (vu::convertApple(events,static_cast<int64_t>(time),frames,batch) != vu::ok) return kAudio_ParamError;
    }
    if (!frames) return noErr;
    StereoBufferList input{}; input.mNumberBuffers=state.channels;
    for (uint32_t channel=0;channel<state.channels;++channel)
        input.mBuffers[channel]={1,bytes,state.inputPlanes.data()+channel*kMaximumFrames};
    const auto pulled=pullInput(flags,timestamp,frames,0,reinterpret_cast<AudioBufferList*>(&input));
    if (pulled != noErr) return pulled;
    if (input.mNumberBuffers != state.channels) return kAudioUnitErr_FormatNotSupported;
    for (uint32_t channel=0;channel<state.channels;++channel) {
        const auto& buffer=input.mBuffers[channel];
        if (buffer.mNumberChannels!=1 || !buffer.mData || buffer.mDataByteSize<bytes) return kAudio_ParamError;
        auto* plane=state.inputPlanes.data()+channel*kMaximumFrames;
        if (buffer.mData!=plane) std::memmove(plane,buffer.mData,bytes);
        for (uint32_t frame=0;frame<frames;++frame) state.interleaved[frame*state.channels+channel]=plane[frame];
    }
    const uint64_t target=state.ingress.read();
    if (target != state.published) {
        if (!vui::ControlIngress::isFeedback(target)) {
            const auto revision=state.session.snapshot().revision;
            if (state.session.edit(vui::ControlIngress::value(target),revision)!=vus::Status::ok) return kAudio_ParamError;
        }
        state.published=target; // Published edit remains pending on any DSP error.
    }
    const auto result=state.session.process(state.interleaved.data(),frames,batch);
    if (result.status!=vus::Status::ok) return kAudio_ParamError;
    if (batch.count) state.ingress.comparePublish(target,batch.events[batch.count-1].target,true);
    for (uint32_t channel=0;channel<state.channels;++channel) {
        auto* plane=state.planes.data()+channel*kMaximumFrames;
        for (uint32_t frame=0;frame<frames;++frame) plane[frame]=state.interleaved[frame*state.channels+channel];
        auto& buffer=output->mBuffers[channel];
        if (buffer.mData) std::memmove(buffer.mData,plane,bytes); else buffer.mData=plane;
        buffer.mDataByteSize=bytes;
    }
    return noErr;
}
}

@implementation VUGainKernel { std::shared_ptr<KernelState> _state; }
- (instancetype)init {
    self=[super init]; if (self) _state=std::make_shared<KernelState>(); return self;
}
- (BOOL)prepareWithMaximumFrames:(uint32_t)frames channels:(uint32_t)channels {
    if (!frames || frames>kMaximumFrames || !channels || channels>kMaximumChannels
        || vu_gain_abi_version()!=1 || vu_gain_max_samples()<frames*channels) return NO;
    _state->prepared.store(false,std::memory_order_release);
    if (_state->session.snapshot().running) _state->session.stop();
    const auto target=_state->ingress.read();
    if (_state->session.edit(vui::ControlIngress::value(target),_state->session.snapshot().revision)!=vus::Status::ok
        || _state->session.start(channels)!=vus::Status::ok) return NO;
    _state->published=target; _state->maximumFrames=frames; _state->channels=channels;
    _state->prepared.store(true,std::memory_order_release); return YES;
}
- (void)releaseResources {
    _state->prepared.store(false,std::memory_order_release);
    if (_state->session.snapshot().running) _state->session.stop();
}
- (BOOL)setLinearGain:(float)gain { return _state->ingress.publish(gain); }
- (uint64_t)stateToken { return _state->ingress.read(); }
- (uint64_t)stateRevision {
    if (_state->prepared.load(std::memory_order_acquire)) return UINT64_MAX;
    return _state->session.snapshot().revision;
}
- (NSData*)copyPrivateStateForToken:(uint64_t)token {
    vus::Bytes data;
    if (vus::encode(vui::ControlIngress::value(token),data)!=vus::Status::ok) return nil;
    return [NSData dataWithBytes:data.data() length:data.size()];
}
- (int32_t)restorePrivateState:(NSData*)data expectedRevision:(uint64_t)revision expectedToken:(uint64_t)token {
    if (_state->prepared.load(std::memory_order_acquire)) return static_cast<int32_t>(vus::Status::activeRestore);
    const auto current=_state->session.snapshot().revision;
    if (revision!=current) return static_cast<int32_t>(vus::Status::staleRevision);
    if (current==UINT64_MAX) return static_cast<int32_t>(vus::Status::exhaustedRevision);
    if (data.length!=vus::wireSize) return static_cast<int32_t>(vus::Status::badLength);
    const void* source=data.bytes;
    if (!source) return static_cast<int32_t>(vus::Status::badPointer);
    vus::Bytes stable;
    std::memcpy(stable.data(),source,stable.size());
    float gain;
    const auto valid=vus::decode(stable.data(),stable.size(),gain);
    if (valid!=vus::Status::ok) return static_cast<int32_t>(valid);
    if (!_state->ingress.comparePublish(token,gain,false)) return static_cast<int32_t>(vus::Status::staleRevision);
    // Every Session rejection was preflighted under its stopped/single-owner contract.
    return static_cast<int32_t>(_state->session.restore(stable.data(),stable.size(),current));
}
- (AUImplementorValueObserver)gainValueObserver {
    auto state=_state;
    return ^(__unsafe_unretained AUParameter*, AUValue value) { state->ingress.publish(value); };
}
- (AUImplementorValueProvider)gainValueProvider {
    auto state=_state;
    return ^AUValue(__unsafe_unretained AUParameter*) { return vui::ControlIngress::value(state->ingress.read()); };
}
- (AUInternalRenderBlock)renderBlock {
    auto state=_state;
    return ^AUAudioUnitStatus(AudioUnitRenderActionFlags* flags,const AudioTimeStamp* timestamp,
        AUAudioFrameCount frames,NSInteger bus,AudioBufferList* output,const AURenderEvent* events,
        __unsafe_unretained AURenderPullInputBlock pullInput) {
        return render(*state,flags,timestamp,frames,bus,output,events,pullInput);
    };
}
- (void)dealloc { _state->prepared.store(false,std::memory_order_release); }
@end
