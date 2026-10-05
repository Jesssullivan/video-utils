#include "ParameterState.hpp"
#include <array>
#include <atomic>
#include <cassert>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <limits>
#include <new>
#include <thread>

static thread_local bool counting = false;
static thread_local uint64_t allocations = 0;
void* operator new(std::size_t n) { if (counting)++allocations; if (auto p=std::malloc(n?n:1))return p; throw std::bad_alloc(); }
void* operator new[](std::size_t n) { return ::operator new(n); }
void operator delete(void* p) noexcept { std::free(p); }
void operator delete[](void* p) noexcept { std::free(p); }
static void near(float a,float b) { assert(std::fabs(a-b)<.000002f); }
static uint32_t bits(float value) { uint32_t b; std::memcpy(&b,&value,sizeof b); return b; }
int main() {
    using namespace vus;
    Bytes unity{}; assert(encode(1,unity)==Status::ok);
    const Bytes golden{'V','U','S','T',1,0,32,0,0x31,0x4e,0x55,0x47,1,0,0,0,
                       0,0,0,0,0,0,0,0,0,0,0x80,0x3f,0,0,0,0};
    assert(unity==golden);
    for(float value:{0.f,-0.f,.25f,1.f,16.f}) { Bytes wire; float output=-1;
      assert(encode(value,wire)==Status::ok); assert(decode(wire.data(),wire.size(),output)==Status::ok);
      assert(bits(output)==bits(value)); }
    for(std::size_t size=0;size<wireSize;++size) { float output=.5;
      assert(decode(unity.data(),size,output)==Status::badLength); near(output,.5); }
    float output=.5;
    assert(decode(unity.data(),33,output)==Status::badLength);
    assert(decode(nullptr,wireSize,output)==Status::badPointer); near(output,.5);
    const std::array<std::pair<unsigned,Status>,7> fields{{{0,Status::badMagic},{4,Status::badSchema},
      {6,Status::badLength},{8,Status::badIdentity},{12,Status::badAbi},{16,Status::badAddress},{28,Status::badReserved}}};
    for(auto [offset,status]:fields) { auto bad=unity; bad[offset]^=0x80;
      assert(decode(bad.data(),bad.size(),output)==status); near(output,.5); }
    for(float value:{-1.f,16.01f,std::numeric_limits<float>::infinity(),
                     -std::numeric_limits<float>::infinity(),std::numeric_limits<float>::quiet_NaN()}) {
      auto bad=unity; auto saved=bad; assert(encode(value,bad)==Status::badGain); assert(bad==saved);
      auto raw=bits(value); for(unsigned i=0;i<4;++i)bad[24+i]=static_cast<uint8_t>(raw>>(8*i));
      assert(decode(bad.data(),bad.size(),output)==Status::badGain); near(output,.5); }
    Session session; auto initial=session.snapshot(); Bytes quarter; assert(encode(.25,quarter)==Status::ok);
    assert(session.restore(quarter.data(),32,initial.revision+1)==Status::staleRevision);
    assert(session.snapshot().revision==0); near(session.snapshot().gain,1);
    auto corrupt=quarter; corrupt[4]=2;
    assert(session.restore(corrupt.data(),32,0)==Status::badSchema); assert(session.snapshot().revision==0);
    assert(session.restore(quarter.data(),32,0)==Status::ok); assert(session.snapshot().revision==1);
    assert(session.restore(unity.data(),32,0)==Status::staleRevision); near(session.snapshot().gain,.25);
    assert(session.start(0)==Status::badChannels); assert(!session.snapshot().running);
    assert(session.start(1)==Status::ok); assert(session.start(2)==Status::alreadyRunning);
    assert(session.restore(unity.data(),32,1)==Status::activeRestore); assert(session.snapshot().revision==1);
    std::array<float,128> audio; audio.fill(1); vu::Batch noEvents;
    assert(session.process(audio.data(),128,noEvents).status==Status::ok); for(float x:audio)near(x,.25);
    assert(session.edit(1,1)==Status::ok); audio.fill(1);
    assert(session.process(audio.data(),128,noEvents).status==Status::ok); near(audio[0],.25); near(audio[32],.625); near(audio[64],1);
    Bytes saved; assert(session.serialize(saved)==Status::ok); float savedGain=0;
    assert(decode(saved.data(),32,savedGain)==Status::ok); near(savedGain,1);
    assert(session.stop()==Status::ok); assert(session.stop()==Status::notRunning);
    assert(session.process(audio.data(),128,noEvents).status==Status::notRunning);
    assert(session.restore(quarter.data(),32,2)==Status::ok); assert(session.start(2)==Status::ok);
    std::array<float,256> stereo; stereo.fill(1);
    assert(session.process(stereo.data(),128,noEvents).status==Status::ok); for(float x:stereo)near(x,.25);
    auto failed=session.process(nullptr,128,noEvents); assert(failed.status==Status::processingFailed); assert(failed.gainStatus==vu::badBuffer);
    assert(session.edit(std::numeric_limits<float>::quiet_NaN(),3)==Status::badGain); assert(session.snapshot().revision==3);
    assert(session.edit(.5,2)==Status::staleRevision); assert(session.snapshot().revision==3);
    Session exhausted(UINT64_MAX); assert(exhausted.edit(.5,UINT64_MAX)==Status::exhaustedRevision);
    assert(exhausted.restore(quarter.data(),32,UINT64_MAX)==Status::exhaustedRevision); near(exhausted.snapshot().gain,1);
    Session last(UINT64_MAX-1); assert(last.restore(quarter.data(),32,UINT64_MAX-1)==Status::ok);
    assert(last.snapshot().revision==UINT64_MAX); assert(last.edit(.5,UINT64_MAX)==Status::exhaustedRevision);
    // Serialization observes control targets, not current ramp/timeline progress.
    vu::Batch step; step.count=1; step.events[0]={0,0,0}; stereo.fill(1);
    assert(session.process(stereo.data(),128,step).status==Status::ok); near(stereo[0],0);
    assert(session.serialize(saved)==Status::ok); assert(decode(saved.data(),32,savedGain)==Status::ok); near(savedGain,.25);
    // One producer may publish while the consumer renders. Lifecycle is fixed.
    Session concurrent; assert(concurrent.start(2)==Status::ok); std::atomic<bool> done{false};
    std::thread producer([&]{for(uint64_t i=0;i<10000;++i)assert(concurrent.edit(float(i%17)/16,i)==Status::ok); done.store(true,std::memory_order_release);});
    unsigned blocks=0;
    do { stereo.fill(1); assert(concurrent.process(stereo.data(),128,noEvents).status==Status::ok);
      for(float x:stereo)assert(std::isfinite(x)&&x>=0&&x<=1); ++blocks;
    } while(!done.load(std::memory_order_acquire)&&blocks<10000);
    producer.join(); assert(concurrent.snapshot().revision==10000);
    counting=true;
    for(unsigned i=0;i<1000;++i) { stereo.fill(1); assert(concurrent.process(stereo.data(),128,noEvents).status==Status::ok); }
    counting=false; assert(allocations==0);
    std::printf("{\"status\":\"passed\",\"wire_bytes\":32,\"render_blocks_allocation_checked\":1000,\"cpp_new_calls\":%llu,\"producer_edits\":10000,\"first_frame_restore_verified\":true,\"au_fullState_implemented\":false,\"logic_host_loaded\":false}\n",(unsigned long long)allocations);
}
