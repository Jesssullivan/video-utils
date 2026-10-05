#include "ParameterState.hpp"
#include <cmath>
#include <cstring>
#include <limits>

namespace vus {
static_assert(sizeof(float) == 4 && std::numeric_limits<float>::is_iec559);
static bool valid(float gain) noexcept { return std::isfinite(gain) && gain >= 0 && gain <= 16; }
static void put(uint8_t* dest, uint64_t value, unsigned width) noexcept {
    for (unsigned i = 0; i < width; ++i) dest[i] = static_cast<uint8_t>(value >> (8 * i));
}
static uint64_t get(const uint8_t* source, unsigned width) noexcept {
    uint64_t value = 0;
    for (unsigned i = 0; i < width; ++i) value |= uint64_t(source[i]) << (8 * i);
    return value;
}
Status encode(float gain, Bytes& output) noexcept {
    if (!valid(gain)) return Status::badGain;
    Bytes next{};
    next[0] = 'V'; next[1] = 'U'; next[2] = 'S'; next[3] = 'T';
    put(next.data()+4, 1, 2); put(next.data()+6, wireSize, 2);
    put(next.data()+8, 0x47554e31, 4); put(next.data()+12, 1, 4);
    uint32_t raw; std::memcpy(&raw, &gain, sizeof raw); put(next.data()+24, raw, 4);
    output = next;
    return Status::ok;
}
Status decode(const uint8_t* bytes, std::size_t size, float& output) noexcept {
    if (size != wireSize) return Status::badLength;
    if (!bytes) return Status::badPointer;
    if (bytes[0] != 'V' || bytes[1] != 'U' || bytes[2] != 'S' || bytes[3] != 'T') return Status::badMagic;
    if (get(bytes+4,2) != 1) return Status::badSchema;
    if (get(bytes+6,2) != wireSize) return Status::badLength;
    if (get(bytes+8,4) != 0x47554e31) return Status::badIdentity;
    if (get(bytes+12,4) != 1) return Status::badAbi;
    if (get(bytes+16,8)) return Status::badAddress;
    if (get(bytes+28,4)) return Status::badReserved;
    uint32_t raw = static_cast<uint32_t>(get(bytes+24,4)); float gain;
    std::memcpy(&gain, &raw, sizeof gain);
    if (!valid(gain)) return Status::badGain;
    output = gain;
    return Status::ok;
}
Status Session::revisionCheck(uint64_t expected) const noexcept {
    if (expected != revision_) return Status::staleRevision;
    if (revision_ == std::numeric_limits<uint64_t>::max()) return Status::exhaustedRevision;
    return Status::ok;
}
Status Session::commit(float gain) noexcept {
    if (!mailbox_.publish(gain)) return Status::badGain;
    gain_ = gain;
    ++revision_;
    return Status::ok;
}
Status Session::restore(const uint8_t* bytes, std::size_t size, uint64_t expectedRevision) noexcept {
    const auto checked = revisionCheck(expectedRevision);
    if (checked != Status::ok) return checked;
    if (engine_) return Status::activeRestore;
    float gain;
    const auto decoded = decode(bytes,size,gain);
    return decoded == Status::ok ? commit(gain) : decoded;
}
Status Session::edit(float gain, uint64_t expectedRevision) noexcept {
    const auto checked = revisionCheck(expectedRevision);
    return checked == Status::ok ? commit(gain) : checked;
}
Status Session::start(uint32_t channels) noexcept {
    if (engine_) return Status::alreadyRunning;
    if (channels < 1 || channels > 2) return Status::badChannels;
    engine_.emplace(mailbox_,channels);
    return Status::ok;
}
Status Session::stop() noexcept {
    if (!engine_) return Status::notRunning;
    engine_.reset();
    return Status::ok;
}
RenderResult Session::process(float* samples, uint32_t frames, const vu::Batch& batch) noexcept {
    if (!engine_) return {Status::notRunning,vu::ok};
    const auto result = engine_->process(samples,frames,batch);
    return {result == vu::ok ? Status::ok : Status::processingFailed,result};
}
}
