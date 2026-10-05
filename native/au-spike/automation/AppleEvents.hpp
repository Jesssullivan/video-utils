#pragma once
#include "GainAutomation.hpp"
#import <AudioToolbox/AudioToolbox.h>

namespace vu {
enum class TimeDomain { renderAbsolute, schedulingInput };
// Caller guarantees live linked nodes for this invocation. No list mutation.
// Delivered render events are absolute. Immediate+offset is scheduling-input only.
Status convertApple(const AURenderEvent* head, int64_t blockStart, uint32_t frames, Batch& output,
                    TimeDomain domain = TimeDomain::renderAbsolute) noexcept;
Status processApple(Engine& engine, float* samples, uint32_t frames, int64_t blockStart, const AURenderEvent* head,
                    TimeDomain domain = TimeDomain::renderAbsolute) noexcept;
}
