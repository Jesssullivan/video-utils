#import "GainKernel.h"
#include "ControlIngress.hpp"
#include "../state/ParameterState.hpp"
#include <array>
#include <algorithm>
#include <atomic>
#include <cassert>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <limits>
#include <new>
#include <thread>

static thread_local bool countNew=false;
static thread_local uint64_t newCalls=0;
void* operator new(size_t n) { if(countNew)++newCalls; if(auto p=std::malloc(n?n:1))return p; throw std::bad_alloc(); }
void* operator new[](size_t n) { return ::operator new(n); }
void operator delete(void* p) noexcept { std::free(p); }
void operator delete[](void* p) noexcept { std::free(p); }
struct StereoList { UInt32 count; AudioBuffer buffers[2]; };
static void near(float a,float b) { assert(std::fabs(a-b)<.000002f); }
static AURenderEvent event(int64_t time,float gain,uint32_t duration=0) {
    AURenderEvent e{}; e.parameter.eventType=duration?AURenderEventParameterRamp:AURenderEventParameter;
    e.parameter.eventSampleTime=time; e.parameter.value=gain; e.parameter.rampDurationSampleFrames=duration; return e;
}
int main() { @autoreleasepool {
    vui::ControlIngress ingress; const auto initial=ingress.read();
    assert(!ingress.publish(NAN)); assert(!ingress.publish(17)); assert(ingress.read()==initial);
    assert(ingress.publish(.5)); const auto old=ingress.read(); assert(ingress.publish(.75));
    assert(!ingress.comparePublish(old,0,true)); near(vui::ControlIngress::value(ingress.read()),.75);
    const auto latest=ingress.read(); assert(ingress.comparePublish(latest,0,true));
    assert(vui::ControlIngress::isFeedback(ingress.read())); assert(ingress.read()!=latest);
    auto zero=ingress.read(); assert(ingress.comparePublish(zero,.5,true));
    auto half=ingress.read(); assert(ingress.comparePublish(half,0,true)); assert(ingress.read()!=zero); // ABA observation ticket.
    auto* kernel=[[VUGainKernel alloc] init]; auto block=kernel.renderBlock;
    auto observer=kernel.gainValueObserver; auto provider=kernel.gainValueProvider;
    AUParameter* parameter=[AUParameterTree createParameterWithIdentifier:@"gain" name:@"Gain" address:0 min:0 max:16
        unit:kAudioUnitParameterUnit_LinearGain unitName:nil flags:kAudioUnitParameterFlag_IsWritable valueStrings:nil dependentParameters:nil];
    vus::Bytes quarter; assert(vus::encode(.25,quarter)==vus::Status::ok);
    NSData* data=[NSData dataWithBytes:quarter.data() length:quarter.size()];
    uint64_t revision=kernel.stateRevision,token=kernel.stateToken;
    assert([kernel restorePrivateState:data expectedRevision:revision+1 expectedToken:token]==static_cast<int32_t>(vus::Status::staleRevision));
    assert([kernel restorePrivateState:data expectedRevision:revision expectedToken:token]==0); near(provider(parameter),.25);
    assert([kernel restorePrivateState:data expectedRevision:revision expectedToken:kernel.stateToken]==static_cast<int32_t>(vus::Status::staleRevision));
    revision=kernel.stateRevision; token=kernel.stateToken; observer(parameter,.5);
    assert([kernel restorePrivateState:data expectedRevision:revision expectedToken:token]==static_cast<int32_t>(vus::Status::staleRevision));
    assert(kernel.stateRevision==revision); near(provider(parameter),.5);
    auto bad=quarter; bad[4]=2; NSData* incompatible=[NSData dataWithBytes:bad.data() length:bad.size()];
    assert([kernel restorePrivateState:incompatible expectedRevision:revision expectedToken:kernel.stateToken]==static_cast<int32_t>(vus::Status::badSchema));
    assert(kernel.stateRevision==revision); near(provider(parameter),.5);
    assert([kernel restorePrivateState:data expectedRevision:revision expectedToken:kernel.stateToken]==0);
    assert([kernel prepareWithMaximumFrames:128 channels:2]);
    assert([kernel restorePrivateState:data expectedRevision:0 expectedToken:kernel.stateToken]==static_cast<int32_t>(vus::Status::activeRestore));
    std::array<float,128> left,right; StereoList out{2,{{1,sizeof left,left.data()},{1,sizeof right,right.data()}}};
    AudioTimeStamp stamp{}; stamp.mFlags=kAudioTimeStampSampleTimeValid; stamp.mSampleTime=100;
    AudioUnitRenderActionFlags flags=0; __block bool invalid=false,failPull=false;
    AURenderPullInputBlock pull=^AUAudioUnitStatus(AudioUnitRenderActionFlags*,const AudioTimeStamp*,AUAudioFrameCount n,NSInteger,AudioBufferList* input) {
        for(uint32_t c=0;c<input->mNumberBuffers;++c) { auto* p=static_cast<float*>(input->mBuffers[c].mData); for(uint32_t f=0;f<n;++f)p[f]=1; }
        if(invalid)static_cast<float*>(input->mBuffers[1].mData)[n-1]=INFINITY;
        if(failPull)return kAudio_ParamError;
        return noErr;
    };
    auto render=[&](uint32_t n,const AURenderEvent* e=nullptr) {out.buffers[0].mDataByteSize=sizeof left;out.buffers[1].mDataByteSize=sizeof right;
        return block(&flags,&stamp,n,0,reinterpret_cast<AudioBufferList*>(&out),e,pull);};
    assert(render(128)==noErr); for(float x:left)near(x,.25); for(float x:right)near(x,.25);
    observer(parameter,1); assert(render(128)==noErr); near(left[0],.25); near(left[32],.625); near(left[64],1);
    auto ramp=event(100,0,256); assert(render(128,&ramp)==noErr); near(left[0],1); near(left[127],129/256.f); near(provider(parameter),0);
    const auto feedbackToken=kernel.stateToken;
    observer(parameter,0);assert(kernel.stateToken==feedbackToken); // Same target is not a ramp-interruption gesture.
    stamp.mSampleTime=228; assert(render(128)==noErr); near(left[0],.5); near(left[127],1/256.f); // Feedback must not restart ramp.
    stamp.mSampleTime=356; assert(render(128)==noErr); near(left[0],0);
    auto step=event(358,.5); assert(render(128,&step)==noErr); near(left[0],0);near(left[1],0);near(left[2],.5);
    const auto preserved=step;
    for(double value:{std::numeric_limits<double>::quiet_NaN(),std::numeric_limits<double>::infinity(),100.5,9223372036854775808.0,-9223372036854777856.0}) {
        stamp.mSampleTime=value; left.fill(-99); assert(render(128,&step)==kAudio_ParamError); near(left[0],-99);
    }
    assert(std::memcmp(&step,&preserved,sizeof step)==0);
    stamp.mFlags=0;stamp.mSampleTime=356;assert(render(128,&step)==kAudio_ParamError);
    stamp.mFlags=kAudioTimeStampSampleTimeValid;
    [kernel releaseResources];observer(parameter,1);assert([kernel prepareWithMaximumFrames:128 channels:2]);
    observer(parameter,0); invalid=true;left.fill(-99);right.fill(-99);
    assert(render(128)==kAudio_ParamError);for(float x:left)near(x,-99);for(float x:right)near(x,-99);
    invalid=false;assert(render(128)==noErr);near(left[0],1);near(left[32],.5);near(left[64],0);
    observer(parameter,1);failPull=true;assert(render(128)==kAudio_ParamError);failPull=false;
    assert(render(0)==noErr);assert(render(128)==noErr);near(left[0],0);near(left[64],1);
    std::atomic<bool> doneA{false},doneB{false};
    std::thread a([&]{for(unsigned i=0;i<10000;++i)observer(parameter,(i%17)/16.f);doneA.store(true,std::memory_order_release);});
    std::thread b([&]{for(unsigned i=0;i<10000;++i)observer(parameter,(i%9)/8.f);doneB.store(true,std::memory_order_release);});
    unsigned renders=0;do {assert(render(128)==noErr);for(float x:left)assert(std::isfinite(x)&&x>=0&&x<=1);++renders;
    }while((!doneA.load(std::memory_order_acquire)||!doneB.load(std::memory_order_acquire))&&renders<10000);
    a.join();b.join();
    countNew=true;for(unsigned i=0;i<1000;++i)assert(render(128)==noErr);countNew=false;assert(newCalls==0);
    observer(parameter,.25); assert(render(128)==noErr);
    out.buffers[0].mData=nullptr;out.buffers[1].mData=nullptr;assert(render(128)==noErr);
    assert(out.buffers[0].mData && out.buffers[1].mData);
    std::array<float,128> ownedLeft,ownedRight;
    std::copy_n(static_cast<float*>(out.buffers[0].mData),128,ownedLeft.begin());
    std::copy_n(static_cast<float*>(out.buffers[1].mData),128,ownedRight.begin());
    observer(parameter,.5);failPull=true;assert(render(128)==kAudio_ParamError);failPull=false;
    assert(std::equal(ownedLeft.begin(),ownedLeft.end(),static_cast<float*>(out.buffers[0].mData)));
    assert(std::equal(ownedRight.begin(),ownedRight.end(),static_cast<float*>(out.buffers[1].mData)));
    invalid=true;assert(render(128)==kAudio_ParamError);invalid=false;
    assert(std::equal(ownedLeft.begin(),ownedLeft.end(),static_cast<float*>(out.buffers[0].mData)));
    assert(std::equal(ownedRight.begin(),ownedRight.end(),static_cast<float*>(out.buffers[1].mData)));
    assert(render(128)==noErr);near(static_cast<float*>(out.buffers[0].mData)[0],.25);
    near(static_cast<float*>(out.buffers[0].mData)[32],.375);near(static_cast<float*>(out.buffers[0].mData)[64],.5);
    [kernel releaseResources];assert(render(128)==kAudioUnitErr_Uninitialized);kernel=nil;
    observer(parameter,.75);near(provider(parameter),.75);assert(render(128)==kAudioUnitErr_Uninitialized);
    vus::Session exhausted(UINT64_MAX); assert(exhausted.edit(.5,UINT64_MAX)==vus::Status::exhaustedRevision);
    std::puts("{\"status\":\"passed\",\"producer_callbacks\":20000,\"render_allocation_blocks\":1000,\"cpp_new_calls\":0,\"planar_automation\":true,\"checked_stopped_state\":true,\"fullState_setter_qualified\":false,\"registered_component\":false}");
} }
