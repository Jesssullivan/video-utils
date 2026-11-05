---
id: narrate-bench-text-v1
written: 2026-10-22
purpose: fixed public narration text for the preregistered engine bench
licence: same as the repository
frozen: true
---

<!--
Written fresh for the bench on 2026-10-22. Every name, place, number and quote below is invented.
Do not edit after the first scored render: a changed text is text-v2 with a new preregistration.
Section ids (s1..s6) are the chunk-group ids the bench reports per section. Only the prose below
the front matter and outside these comments is spoken.
-->

## s1 Opening

On the north side of the valley, a small weather station has been running since the spring of 1987. It sits on a concrete pad behind the old grain elevator, two hundred and forty metres above the river, and for most of its life nobody paid it much attention. It counted rain, it measured wind, and every night at 11:58 p.m. it sent a short report to a computer that most people in town had forgotten existed.

This is the story of how that station was rebuilt over one cold winter, and what the people who rebuilt it learned about listening carefully.

## s2 The fault

The trouble started in late November. The anemometer, the spinning cup assembly that measures wind speed, began to report gusts of 140 kilometres per hour on calm afternoons. At first the volunteers assumed a loose bearing. They replaced it, and the readings got worse. By the first week of December the station claimed a hurricane every Tuesday at roughly 3:15 in the afternoon.

Marguerite Okonkwo, a retired electrical engineer who had looked after the station for nine years, finally connected an oscilloscope to the signal line. The pulses from the anemometer were clean. Riding on top of them, though, was a burst of noise at about 48 kilohertz, appearing and disappearing on a regular schedule. Something nearby was switching on, flooding the cable with interference, and switching off again.

## s3 The conversation

She called her neighbour, Tobias Lindqvist, who ran the hardware shop on Mill Street.

"Tobias, does anything around the elevator turn on at a quarter past three on Tuesdays?"

He thought about it for a moment. "The feed mill runs its big dryer on Tuesdays. Why?"

"Because I think your dryer is pretending to be a hurricane."

"That would explain the forecasts," he said. "My wife cancelled two picnics."

"Tell her I'm sorry. Can you find out what drives the motor?"

"I can do better than that. I'll bring the manual and a thermos of coffee."

## s4 The rebuild

The manual showed a variable frequency drive, a box of power electronics that lets a large motor change speed smoothly. Drives like that are efficient, but a poorly grounded one can push high frequency noise into every unshielded wire within a few dozen metres. The station's sensor cable, installed in 1987, had no shielding at all.

The volunteers made a plan with three parts. First, they would replace the twenty-two metres of sensor cable with shielded, twisted pair wire, grounded at one end only. Second, they would move the data logger into a sealed metal enclosure. Third, they would add a simple software check: any gust more than 2.5 times the average of the surrounding minute would be flagged for a human to review, rather than silently recorded.

The materials cost $1,284.60, which the town council approved on a vote of six to one. The single objection came from a councillor who wanted to know whether the station could also forecast the price of diesel. It could not.

Installation took four Saturdays in January. The ground was frozen solid, so the trench for the new conduit was cut with a rented saw and a great deal of patience. On the third Saturday the temperature fell to minus 19 degrees Celsius, and the epoxy for the cable glands refused to cure until somebody brought a hair dryer from home.

## s5 What the numbers showed

When the station came back online on the 28th of January, the phantom gusts were gone. Over the following eight weeks the volunteers compared its readings against a calibrated portable unit borrowed from the regional college. Wind speed agreed to within 0.4 metres per second on 96 percent of samples. Rainfall totals matched to the nearest millimetre on every day but one, and on that day a curious crow had been sitting in the portable gauge.

The software check turned out to be the most useful part of the project. In March it flagged a genuine gust of 87 kilometres per hour during a thunderstorm, and the flag sat beside the reading in the archive with a short note from the person who reviewed it. Nobody had to wonder, years later, whether the number was real.

## s6 Closing

Marguerite likes to say that the station never lied. It reported exactly what reached it, and what reached it was the sound of a dryer two buildings away. The lesson she draws from the winter is a modest one. Before you trust a measurement, find out what else your instrument can hear. And when a number looks impossible, write down why you believed it, or why you did not, so that the next person does not have to start from the beginning.

The station is still running. Every night at 11:58 p.m. it sends its short report, and now, at least, somebody reads it.
