#pragma once
#include "../automation/GainAutomation.hpp"
#include <array>
#include <cstddef>
#include <cstdint>
#include <optional>

namespace vus {
constexpr std::size_t wireSize = 32;
using Bytes = std::array<uint8_t, wireSize>;
enum class Status { ok, badLength, badPointer, badMagic, badSchema, badIdentity,
                    badAbi, badAddress, badReserved, badGain, staleRevision,
                    exhaustedRevision, activeRestore, alreadyRunning,
                    notRunning, badChannels, processingFailed };
Status encode(float gain, Bytes& output) noexcept;
Status decode(const uint8_t* bytes, std::size_t size, float& output) noexcept;
struct Snapshot { float gain; uint64_t revision; bool running; };
struct RenderResult { Status status; vu::Status gainStatus; };

// Exactly one serialized control owner, one audio consumer. start/stop require
// every render call stopped; this API does not stop or synchronize host threads.
class Session {
public:
    explicit Session(uint64_t initialRevision = 0) noexcept : revision_(initialRevision) {}
    Snapshot snapshot() const noexcept { return {gain_, revision_, engine_.has_value()}; }
    Status serialize(Bytes& output) const noexcept { return encode(gain_, output); }
    Status restore(const uint8_t* bytes, std::size_t size, uint64_t expectedRevision) noexcept;
    Status edit(float gain, uint64_t expectedRevision) noexcept;
    Status start(uint32_t channels) noexcept;
    Status stop() noexcept;
    RenderResult process(float* samples, uint32_t frames, const vu::Batch& batch) noexcept;
private:
    Status revisionCheck(uint64_t expected) const noexcept;
    Status commit(float gain) noexcept;
    vu::Mailbox mailbox_;
    std::optional<vu::Engine> engine_;
    float gain_ = 1;
    uint64_t revision_;
};
}
