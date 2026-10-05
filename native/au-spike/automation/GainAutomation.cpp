#include "GainAutomation.hpp"
#include "../include/video_utils_gain.h"
#include <cmath>
#include <cstring>
#include <limits>

namespace vu {
static bool validGain(float value) noexcept { return std::isfinite(value) && value >= 0 && value <= 16; }
static uint32_t bits(float value) noexcept { uint32_t result; std::memcpy(&result, &value, sizeof result); return result; }
Mailbox::Mailbox(float initial) noexcept : word_(bits(validGain(initial) ? initial : 1.0f)) {}
float Mailbox::value(uint64_t word) noexcept { uint32_t raw = static_cast<uint32_t>(word); float result; std::memcpy(&result, &raw, sizeof result); return result; }
bool Mailbox::publish(float value) noexcept {
    if (!validGain(value)) return false;
    ++generation_;
    word_.store((uint64_t(generation_) << 32) | bits(value), std::memory_order_release);
    return true;
}
Engine::Engine(Mailbox& mailbox, uint32_t channels) noexcept : mailbox_(mailbox), channels_(channels) {
    state_.seen = mailbox_.read();
    state_.current = state_.start = state_.target = Mailbox::value(state_.seen);
}
void Engine::begin(State& state, float target, uint32_t duration) noexcept {
    state.start = state.current;
    state.target = target;
    state.duration = duration;
    state.elapsed = 0;
    if (!duration) state.current = target;
}
void Engine::advance(State& state) noexcept {
    if (!state.duration) return;
    ++state.elapsed;
    if (state.elapsed >= state.duration) { state.current = state.target; state.duration = 0; }
    else state.current = state.start + (state.target - state.start) * (double(state.elapsed) / state.duration);
}
Status Engine::process(float* samples, uint32_t frames, const Batch& batch) noexcept {
    if (frames > maxFrames || channels_ < 1 || channels_ > 2) return badSize;
    if (batch.count > maxEvents) return badEvent;
    for (uint32_t i = 0; i < batch.count; ++i) {
        const auto& event = batch.events[i];
        if (event.offset >= frames || event.duration > maxRamp || !validGain(event.target)
            || (i && event.offset < batch.events[i-1].offset)) return badEvent;
    }
    if (!frames) return ok; // No consumption or ramp advancement on an empty block.
    if (!samples || reinterpret_cast<uintptr_t>(samples) % alignof(float)) return badBuffer;
    State next = state_;
    const uint64_t latest = mailbox_.read(); // One bounded read, no retry loop.
    if (latest != next.seen) { begin(next, Mailbox::value(latest), 64); next.seen = latest; }
    uint32_t eventIndex = 0;
    for (uint32_t frame = 0; frame < frames; ++frame) {
        while (eventIndex < batch.count && batch.events[eventIndex].offset == frame) {
            const auto& event = batch.events[eventIndex++];
            begin(next, event.target, event.duration);
        }
        gains_[frame] = static_cast<float>(next.current);
        advance(next);
    }
    const uint32_t count = frames * channels_;
    for (uint32_t i = 0; i < count; ++i) {
        if (!std::isfinite(samples[i])) return badSample;
        if (std::fabs(double(samples[i]) * gains_[i / channels_]) > std::numeric_limits<float>::max()) return overflow;
        scratch_[i] = samples[i];
    }
    for (uint32_t frame = 0; frame < frames; ++frame)
        if (vu_gain_process(scratch_.data() + frame * channels_, channels_, gains_[frame]) != VU_OK) return ffiError;
    std::memcpy(samples, scratch_.data(), count * sizeof(float));
    state_ = next;
    return ok;
}
} // namespace vu
