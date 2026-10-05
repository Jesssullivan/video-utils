#pragma once
#include <atomic>
#include <cstdint>

namespace vui {
// Multi-producer latest target. Exchange order is authoritative, not ticket order.
class ControlIngress {
public:
    uint64_t read() const noexcept { return word_.load(std::memory_order_acquire); }
    bool publish(float value) noexcept;
    bool comparePublish(uint64_t expected, float value, bool feedback) noexcept;
    static float value(uint64_t word) noexcept;
    static bool isFeedback(uint64_t word) noexcept { return (word >> 32 & 1) == 0; }
private:
    uint64_t candidate(float value, bool feedback) noexcept;
    std::atomic<uint64_t> word_{(uint64_t(1) << 32) | 0x3f800000};
    std::atomic<uint32_t> ticket_{1}; // 31-bit publication ticket plus source bit.
};
static_assert(std::atomic<uint64_t>::is_always_lock_free);
static_assert(std::atomic<uint32_t>::is_always_lock_free);
}
