#include "ControlIngress.hpp"
#include <cmath>
#include <cstring>

namespace vui {
static bool valid(float value) noexcept { return std::isfinite(value) && value >= 0 && value <= 16; }
float ControlIngress::value(uint64_t word) noexcept {
    const uint32_t raw = static_cast<uint32_t>(word); float result;
    std::memcpy(&result,&raw,sizeof result); return result;
}
uint64_t ControlIngress::candidate(float value, bool feedback) noexcept {
    uint32_t raw; std::memcpy(&raw,&value,sizeof raw);
    const uint32_t tag = (ticket_.fetch_add(1,std::memory_order_relaxed) << 1) | uint32_t(!feedback);
    return (uint64_t(tag) << 32) | raw;
}
bool ControlIngress::publish(float value) noexcept {
    if (!valid(value)) return false;
    uint32_t raw; std::memcpy(&raw,&value,sizeof raw);
    if (static_cast<uint32_t>(read()) == raw) return true; // Idempotent target, not a new gesture.
    word_.exchange(candidate(value,false),std::memory_order_acq_rel);
    return true;
}
bool ControlIngress::comparePublish(uint64_t expected, float value, bool feedback) noexcept {
    if (!valid(value)) return false;
    return word_.compare_exchange_strong(expected,candidate(value,feedback),std::memory_order_acq_rel,std::memory_order_acquire);
}
}
