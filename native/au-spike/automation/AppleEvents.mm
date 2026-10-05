#include "AppleEvents.hpp"
#include <cmath>

namespace vu {
Status convertApple(const AURenderEvent* head, int64_t blockStart, uint32_t frames, Batch& output, TimeDomain domain) noexcept {
    if (frames > maxFrames) return badSize;
    Batch next;
    for (auto* node = head; node; node = node->head.next) {
        if (next.count == maxEvents) return badEvent; // Bounded even for a cycle.
        if (node->head.eventType != AURenderEventParameter && node->head.eventType != AURenderEventParameterRamp) return badEvent;
        const auto& parameter = node->parameter;
        if (parameter.reserved[0] || parameter.reserved[1] || parameter.reserved[2]
            || parameter.parameterAddress != 0 || !std::isfinite(parameter.value)
            || parameter.value < 0 || parameter.value > 16 || parameter.rampDurationSampleFrames > maxRamp
            || (parameter.eventType == AURenderEventParameter && parameter.rampDurationSampleFrames)
            || (parameter.eventType == AURenderEventParameterRamp && !parameter.rampDurationSampleFrames)) return badEvent;
        uint64_t offset;
        const int64_t time = parameter.eventSampleTime;
        if (domain == TimeDomain::schedulingInput && time >= AUEventSampleTimeImmediate && time < AUEventSampleTimeImmediate + int64_t(maxFrames))
            offset = uint64_t(time - AUEventSampleTimeImmediate);
        else {
            if (time < blockStart) return badEvent;
            offset = uint64_t(time) - uint64_t(blockStart); // Unsigned subtraction avoids signed overflow.
        }
        if (offset >= frames || (next.count && offset < next.events[next.count-1].offset)) return badEvent;
        next.events[next.count++] = {static_cast<uint32_t>(offset), parameter.rampDurationSampleFrames, parameter.value};
    }
    output = next;
    return ok;
}
Status processApple(Engine& engine, float* samples, uint32_t frames, int64_t blockStart, const AURenderEvent* head, TimeDomain domain) noexcept {
    Batch batch;
    const auto status = convertApple(head, blockStart, frames, batch, domain);
    return status == ok ? engine.process(samples, frames, batch) : status;
}
}
