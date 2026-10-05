#pragma once
#include <array>
#include <atomic>
#include <cstdint>

namespace vu {
constexpr uint32_t maxFrames = 4096, maxEvents = 32, maxRamp = 192000;
enum Status { ok = 0, badBuffer, badSize, badEvent, badSample, overflow, ffiError };
struct Event { uint32_t offset, duration; float target; };
struct Batch { std::array<Event, maxEvents> events{}; uint32_t count = 0; };

// One serialized producer; exactly one audio consumer. Latest edits coalesce.
class Mailbox {
public:
    explicit Mailbox(float initial = 1.0f) noexcept;
    bool publish(float value) noexcept;
    uint64_t read() const noexcept { return word_.load(std::memory_order_acquire); }
    static float value(uint64_t word) noexcept;
private:
    std::atomic<uint64_t> word_;
    uint32_t generation_ = 0; // producer-only; wrap after 2^32 edits is documented
};
static_assert(std::atomic<uint64_t>::is_always_lock_free);

class Engine {
public:
    explicit Engine(Mailbox& mailbox, uint32_t channels = 1) noexcept;
    Status process(float* samples, uint32_t frames, const Batch& events) noexcept;
    double current() const noexcept { return state_.current; }
private:
    struct State { double current = 1, start = 1, target = 1; uint32_t duration = 0, elapsed = 0; uint64_t seen = 0; };
    static void begin(State&, float target, uint32_t duration) noexcept;
    static void advance(State&) noexcept;
    Mailbox& mailbox_;
    uint32_t channels_;
    State state_;
    std::array<float, maxFrames> gains_{};
    std::array<float, maxFrames * 2> scratch_{};
};
} // namespace vu
