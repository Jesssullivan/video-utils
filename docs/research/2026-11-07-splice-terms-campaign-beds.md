# Splice terms for campaign music beds

Read November 7, 2026 from public pages, for TIN-7788 item 2.8 under ruling TIN-7125 `e552e569`. This is a reading of public text, not legal advice. Quotes are verbatim and short. "Refuses" below means the code or the use must stop on that term.

## Sources

| Id | Source | Date on page |
| --- | --- | --- |
| T | [Splice Terms of Use](https://splice.com/terms) | Last Updated November 2, 2026 |
| F | [Splice Sounds Licensing FAQ](https://support.splice.com/en/articles/8652642-splice-sounds-licensing-faq) | September 6, 2024 |
| M | [Getting Started with the Splice MCP Server (Beta)](https://support.splice.com/en/articles/14442749-getting-started-with-the-splice-mcp-server-beta) | April 6, 2026 |
| L | [How do I generate a certified license](https://support.splice.com/en/articles/8652641-how-do-i-generate-a-certified-license-for-my-samples) | "Updated over 2 weeks ago" |
| B | [Generate a certified license for your Splice samples](https://splice.com/blog/generate-certified-license/) | January 26, 2023 |

The November 2 terms renumbered the Sounds licence to section 2.3.1. F still links to "Section 3.1.1.3" for what T now calls 2.3.1.4.

## What they allow

| Use | Text | Source |
| --- | --- | --- |
| Commercial video | "non-exclusive, non-transferable, perpetual right to use Sounds", in works "such as but not limited to, video games, film or television projects (including synchronization uses), radio, live performances, and social media videos", for "non-commercial and commercial purposes" | T 2.3.1.3 |
| Commercial upload | Commercial use includes "uploading a Creative Work or New Recording to a third-party media platform for purposes of monetization" | F |
| Royalties and credit | "a royalty-free license for every sound". "you do not need to provide credit" | F |
| A loop alone inside a video | Creative Works may use Sounds "used either in isolation as sound effects, loops, and/or sound mixes" | T 2.3.1.3 |
| Distribution inside the work | "you may modify, reproduce, publicly perform, distribute, transmit, communicate to the public, sublicense and otherwise use Sounds as embodied in a Creative Work" | T 2.3.1.3 |
| Agent search and download | "download sounds directly inside AI tools like Claude". "The AI returns matching results and downloads your selection using your credits" | M |
| Cost | "Downloading a new sample costs 1 credit. Re-downloads are free". "up to 100 samples per rolling 24-hour period" | M |
| After a cancellation | "the sounds you've downloaded remain covered" | F |

## Content ID

T does not mention Content ID. Splice's other pages give no clearance and no pre-upload check.

| Text | Source |
| --- | --- |
| "While we can't guarantee that your tracks won't get flagged, this certified license will be all you need to show proof that you can use the sample legally, dispute the claim" | F, also B |
| Claims arise on "vocal samples, long instrumental loops, and other samples that are likely to be used in full, without alteration" | B |
| "services may require exclusive rights to all source content (such as individual samples), which is not possible with samples from Splice Sounds" | F |

Inference: a claim can follow a licensed bed, so Content ID is a watch item after upload and no check before it can close. Inference: do not enrol a video with a bed as an owned asset in Content ID or a similar exclusive-rights programme. The 2 or 3 layer rule stays a house rule, because B names full unaltered loops as the case that gets flagged, and T asks for no arrangement.

## What would refuse

| # | Term | Text | Effect here |
| --- | --- | --- | --- |
| 1 | Stand-alone loops | "you may not (a) sublicense the Sounds in isolation as sound effects, loops, or as source material for any other form of sample (even if you modify the Sounds)". FAQ: "you may not distribute any Splice Sounds as royalty-free samples or loops" | Refuses publishing a bed on its own. `bed.wav`, the ducked stem and raw loops stay private |
| 2 | Leaving the account | Do not "share, lend, broadcast, rent, lease, assign, distribute, or transfer the Sounds to a third party except as incorporated into a New Recording or Creative Work" (T 2.3.1.4 (c)) | Refuses raw loops on a rented GPU, a hosted engine, or in a handoff package to anyone else. Inference: a rented render of the mix needs the bed mixed locally first |
| 3 | Preview audio | A "preview" Sound may only be used "to internally and locally (on the Services) preview" it (T 2.3.1.4 (f)) | Refuses a preview file in a bed. Inference: it also refuses analysing one off the service. `pick` skips a preview row, so fit is judged from catalog data until a purchased file arrives |
| 4 | Use without credits | Do not "use the Sounds without spending Credits" outside a promotion or an unsaved Stack (T 2.3.1.4 (g)) | Every layer comes through the purchase route |
| 5 | Stacks | "A Stack on its own is not deemed a New Recording or Creative Work", and "You must expend Credits ... to copy, export and/or download a Stack" (T 2.5). "Shared links are public" (M) | The port has no stack export and no share method |
| 6 | AI training | Do not "use the Sounds as source or training material for generative or other types of artificial intelligence models" (T 2.3.1.4 (h), also 2.12 (o)) | Refuses a cut with a bed as voice, likeness or other model training input. Keep voice stems for that use. Choosing a bed from catalog data is no training |
| 7 | Scrapers | Do not "use any manual or automated software ... to \"scrape\" or download data from any web pages" (T 2.12 (j)) | Refuses any adapter other than Splice's own MCP server. A browser or HTTP adapter stays out |
| 8 | Artist name | "you may not use the name, image, or likeness of any artist associated with a Sound in any way without that artist's express written permission" (T 2.3.1.4) | No loop name, pack or creator enters an output or a description |
| 9 | Business accounts | Do not, "if you are a business entity, use the Services ... in connection with more than one individual affiliated with that entity per Account" (T 2.12 (n)). Credentials: "fully responsible for all activities" (T 3.2) | Open. See below |
| 10 | Breach | "Any unauthorized use of the Services or DCI Property terminates the licenses" (T 2.12) | A breach reaches every bed, so these stay code rules |

## Open and unknown

- **The certified licence has no agent route.** T makes it optional evidence: "you may obtain a copy". L generates it in the website or desktop app, and asks for "your full legal name". The MCP tools hold search, stacks and download, with no licence tool. So `certifiedPdfSha256` stays null on an agent's record, and `deliver_check` keeps `public_upload_allowed` false while it does.
- **A public cut with a bed still refuses in code.** `deliver_check` requires the PDF digest and a clear Content ID result, and neither has an agent route. Neither is a Splice condition of use. Moving them for campaign jobs belongs to the campaign edition, item 2.6, and is not done here.
- **Which account.** A signed-in person is the only case M describes. T 2.12 (n) binds a business entity to one individual per account, and the licence is "non-transferable". Whether xoxd.ai's campaign is served by one person's account is for Jess, under the legal boundary in TIN-2345.
- **Unattended use.** M describes a person talking to a client after a browser login, and no text permits or refuses a worker holding that session. A session that expires makes the port fail. Beta features "may be modified or discontinued" (T 9.1).
- **The tool's own text.** `download_asset` says "Always confirm with the user before calling this tool", and `describe_a_sound` says to let the user decide among results. Those are the server's instructions to a model, not licence terms. Jess's standing answer in `e552e569` is that confirmation, so the adapter needs a line saying so.
- **Plan and balance.** M requires a "Sounds+, Creator, or Creator+ subscription to download samples". The plan and its monthly credits were not read, because that needs the account. No MCP tool reads a balance, so the guard counts this stage's spend and holds a project budget. A bed costs 2 or 3 credits, so a video a day costs at most 93 in a 31 day month.
- **Generated audio.** T 12.6.1 gives no warranty on AI-Generated Content: "You are responsible for reviewing". The port buys catalog Sounds only.

## Limitations

Only the five pages above were read, plus the two MCP tool descriptions. No Certified License PDF was opened, so its wording is unverified. No YouTube page was read. F and B are older than T, and T governs where they differ. T may change: "Any changes to the Agreement will be effective ... on the stated Effective Date for existing Users". A bed record names the terms and date it read, so re-read T before a new catalog adapter or a paid delivery.
