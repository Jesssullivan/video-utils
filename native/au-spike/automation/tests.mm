#include "AppleEvents.hpp"
#include <algorithm>
#include <array>
#include <cassert>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <limits>
#include <new>
#include <thread>

static thread_local bool counting = false;
static thread_local uint64_t allocations = 0;
void* operator new(std::size_t size) { if (counting) ++allocations; if (void* p = std::malloc(size ? size : 1)) return p; throw std::bad_alloc(); }
void* operator new[](std::size_t size) { return ::operator new(size); }
void operator delete(void* p) noexcept { std::free(p); }
void operator delete[](void* p) noexcept { std::free(p); }
static void close(float a, float b) { assert(std::fabs(a-b) < 0.000002f); }
static AURenderEvent event(int64_t time, float value, uint32_t duration = 0) {
    AURenderEvent result{};
    result.parameter.eventType = duration ? AURenderEventParameterRamp : AURenderEventParameter;
    result.parameter.eventSampleTime = time;
    result.parameter.value = value;
    result.parameter.rampDurationSampleFrames = duration;
    return result;
}
int main() {
    using namespace vu;
    Batch empty;
    { Mailbox mailbox; Engine engine(mailbox); std::array<float, 8> audio; audio.fill(1);
      auto e = event(102, 0); auto before = e;
      assert(processApple(engine, audio.data(), 8, 100, &e) == ok);
      assert(std::memcmp(&e, &before, sizeof e) == 0);
      for (unsigned i=0;i<8;++i) close(audio[i], i<2 ? 1 : 0); }
    { Mailbox mailbox; Engine engine(mailbox); std::array<float, 8> audio; audio.fill(1);
      auto e = event(AUEventSampleTimeImmediate+2, 0, 4);
      assert(processApple(engine, audio.data(), 8, 100, &e, TimeDomain::schedulingInput) == ok);
      const float expected[]{1,1,1,.75,.5,.25,0,0};
      for (unsigned i=0;i<8;++i) close(audio[i], expected[i]); }
    { Mailbox mailbox; Engine engine(mailbox, 2); std::array<float, 8> audio; audio.fill(1);
      auto ramp = event(0, 0, 8);
      assert(processApple(engine, audio.data(), 4, 0, &ramp) == ok);
      for (unsigned i=0;i<4;++i) { close(audio[i*2], 1-i/8.f); close(audio[i*2+1], audio[i*2]); }
      audio.fill(1); assert(engine.process(audio.data(), 4, empty) == ok);
      for (unsigned i=0;i<4;++i) close(audio[i*2], .5-i/8.f);
      close(float(engine.current()),0); }
    { Mailbox mailbox; Engine engine(mailbox,2); std::array<float,maxFrames*2> audio; audio.fill(1);
      auto e=event(maxFrames-1,.5f);
      assert(processApple(engine,audio.data(),maxFrames,0,&e)==ok);
      close(audio[maxFrames*2-3],1); close(audio[maxFrames*2-2],.5f); close(audio.back(),.5f); }
    { Mailbox mailbox; Engine engine(mailbox); std::array<float,8> audio; audio.fill(1);
      auto a=event(0,0,8), b=event(4,1,4); a.head.next=&b;
      assert(processApple(engine,audio.data(),8,0,&a)==ok);
      const float expected[]{1,.875,.75,.625,.5,.625,.75,.875};
      for (unsigned i=0;i<8;++i) close(audio[i],expected[i]);
      auto c=event(8,.25f),d=event(8,.75f); c.head.next=&d; audio.fill(1);
      assert(processApple(engine,audio.data(),8,8,&c)==ok); close(audio[0],.75f); }
    float smoothJump = 0;
    { Mailbox mailbox; Engine engine(mailbox); std::array<float,128> audio; audio.fill(1);
      assert(mailbox.publish(0)); assert(engine.process(nullptr,0,empty)==ok); close(float(engine.current()),1);
      assert(engine.process(audio.data(),128,empty)==ok);
      for (unsigned i=1;i<128;++i) smoothJump=std::max(smoothJump,std::fabs(audio[i]-audio[i-1]));
      close(smoothJump,1/64.f); close(audio[64],0);
      assert(!mailbox.publish(std::numeric_limits<float>::quiet_NaN())); assert(!mailbox.publish(17));
      assert(mailbox.publish(.5)); assert(mailbox.publish(.25)); audio.fill(1);
      assert(engine.process(audio.data(),128,empty)==ok); close(audio[64],.25); }
    { Mailbox mailbox; Engine engine(mailbox); std::array<float,4> audio{1,2,3,4}; const auto saved=audio;
      assert(engine.process(nullptr,4,empty)==badBuffer);
      alignas(float) std::array<unsigned char,32> storage{};
      assert(engine.process(reinterpret_cast<float*>(storage.data()+1),4,empty)==badBuffer);
      assert(engine.process(audio.data(),maxFrames+1,empty)==badSize);
      Engine invalid(mailbox,3); assert(invalid.process(audio.data(),4,empty)==badSize);
      Batch batch; batch.count=33; assert(engine.process(audio.data(),4,batch)==badEvent);
      batch.count=1; batch.events[0]={4,0,1}; assert(engine.process(audio.data(),4,batch)==badEvent);
      batch.events[0]={0,maxRamp+1,1}; assert(engine.process(audio.data(),4,batch)==badEvent);
      batch.events[0]={0,0,std::numeric_limits<float>::infinity()}; assert(engine.process(audio.data(),4,batch)==badEvent);
      assert(audio==saved); assert(mailbox.publish(0)); audio[3]=std::numeric_limits<float>::quiet_NaN();
      assert(engine.process(audio.data(),4,empty)==badSample); close(float(engine.current()),1);
      audio.fill(1); assert(engine.process(audio.data(),4,empty)==ok); close(audio[0],1); close(audio[1],63/64.f);
      Mailbox loud(16); Engine loudEngine(loud); audio.fill(std::numeric_limits<float>::max()); const auto loudSaved=audio;
      assert(loudEngine.process(audio.data(),4,empty)==overflow); assert(audio==loudSaved); }
    { Batch result; result.count=1; result.events[0]={3,0,.3f}; const auto saved=result;
      auto e=event(100,1); e.parameter.parameterAddress=1;
      assert(convertApple(&e,100,8,result)==badEvent); assert(std::memcmp(&result,&saved,sizeof result)==0);
      e=event(100,1); e.parameter.reserved[2]=1; assert(convertApple(&e,100,8,result)==badEvent);
      e=event(100,1); e.head.eventType=AURenderEventMIDI; assert(convertApple(&e,100,8,result)==badEvent);
      e=event(99,1); assert(convertApple(&e,100,8,result)==badEvent);
      e=event(108,1); assert(convertApple(&e,100,8,result)==badEvent);
      e=event(AUEventSampleTimeImmediate+8,1); assert(convertApple(&e,100,8,result,TimeDomain::schedulingInput)==badEvent);
      e=event(INT64_MAX,1); assert(convertApple(&e,INT64_MIN,8,result)==badEvent);
      e=event(INT64_MIN+2,1); assert(convertApple(&e,INT64_MIN,8,result)==ok); assert(result.events[0].offset==2);
      e=event(INT64_MAX,1); assert(convertApple(&e,INT64_MAX-3,8,result)==ok); assert(result.events[0].offset==3);
      auto a=event(102,1), b=event(101,1); a.head.next=&b; assert(convertApple(&a,100,8,result)==badEvent);
      e=event(100,1); e.head.next=&e; assert(convertApple(&e,100,8,result)==badEvent);
      std::array<AURenderEvent,33> list; for(unsigned i=0;i<33;++i) { list[i]=event(100,1); if(i<32)list[i].head.next=&list[i+1]; }
      assert(convertApple(list.data(),100,8,result)==badEvent); list[31].head.next=nullptr;
      assert(convertApple(list.data(),100,8,result)==ok); assert(result.count==32);
      assert(convertApple(list.data(),100,0,result)==badEvent);
      e=event(AUEventSampleTimeImmediate+4095,0,maxRamp);
      assert(convertApple(&e,0,maxFrames,result,TimeDomain::schedulingInput)==ok); assert(result.events[0].offset==4095);
      e=event(AUEventSampleTimeImmediate+2,1);
      assert(convertApple(&e,AUEventSampleTimeImmediate-2,8,result)==ok); assert(result.events[0].offset==4);
      assert(convertApple(&e,AUEventSampleTimeImmediate+10,8,result)==badEvent);
      e=event(100,std::numeric_limits<float>::quiet_NaN()); assert(convertApple(&e,100,8,result)==badEvent);
      e=event(100,1); e.head.eventType=AURenderEventParameterRamp; assert(convertApple(&e,100,8,result)==badEvent);
      e=event(100,1,maxRamp+1); assert(convertApple(&e,100,8,result)==badEvent); }
    // Concurrent producer/consumer stress exercises the actual lock-free mailbox.
    { Mailbox mailbox; Engine engine(mailbox); std::atomic<bool> done{false};
      std::thread producer([&]{for(unsigned i=0;i<20000;++i)assert(mailbox.publish((i%17)/16.f)); done.store(true,std::memory_order_release);});
      std::array<float,128> audio; unsigned blocks=0;
      do { audio.fill(1); assert(engine.process(audio.data(),128,empty)==ok); for(float x:audio)assert(std::isfinite(x)&&x>=0&&x<=1); ++blocks; } while(!done.load(std::memory_order_acquire) && blocks<20000);
      producer.join(); }
    Mailbox mailbox; Engine engine(mailbox,2); std::array<float,256> audio; std::array<double,10000> times{};
    Batch batch; batch.count=2; batch.events[0]={0,64,.25}; batch.events[1]={96,16,1};
    auto a=event(0,.25f,64),b=event(96,1,16); a.head.next=&b;
    const auto aBefore=a,bBefore=b;
    counting=true;
    for(unsigned i=0;i<1000;++i) { audio.fill(1); assert(processApple(engine,audio.data(),128,0,&a)==ok); }
    counting=false; assert(allocations==0);
    assert(std::memcmp(&a,&aBefore,sizeof a)==0); assert(std::memcmp(&b,&bBefore,sizeof b)==0);
    double sum=0,maximum=0; unsigned nominalDeadlineExceeds=0;
    for(auto& sample:times) { audio.fill(1); const auto start=std::chrono::steady_clock::now();
      assert(engine.process(audio.data(),128,batch)==ok);
      sample=std::chrono::duration<double,std::micro>(std::chrono::steady_clock::now()-start).count(); sum+=sample; maximum=std::max(maximum,sample);
      if(sample>128/48000.0*1000000)++nominalDeadlineExceeds; }
    std::sort(times.begin(),times.end());
    std::printf("{\"status\":\"passed\",\"benchmark_blocks\":10000,\"frames\":128,\"channels\":2,\"cpp_new_calls_during_1000_blocks\":%llu,\"mean_us\":%.3f,\"median_us\":%.3f,\"p95_us\":%.3f,\"max_us\":%.3f,\"nominal_48k_deadline_exceeded_blocks\":%u,\"ui_ramp_max_jump\":%.6f,\"explicit_step_jump\":1.0,\"host_qualified\":false}\n",(unsigned long long)allocations,sum/times.size(),times[5000],times[9500],maximum,nominalDeadlineExceeds,smoothJump);
}
