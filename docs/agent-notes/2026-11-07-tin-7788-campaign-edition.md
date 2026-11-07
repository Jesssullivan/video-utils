# Campaign edition, machine verdict and look route (November 7, 2026)

Linear TIN-7788, rulings TIN-7125 `52ca88bf` and `0690fe88`, plan item 2.6, video-utils half. Receipt cites
R-HOOK-CONVERGENCE-20261004 (R-N13). Nothing ran on a GPU, an engine or a Hatchet row. Fixtures are synthetic. Off by
default: nothing calls `campaign-verdict`, and nothing here publishes.

`campaign edition | narrate lane | video-utils feat/tin-7788-campaign-edition, base #98 head 5f4efaec | local tests in the PR | root integrates`

## What changed

| File | Change |
| --- | --- |
| `narrate/video/campaign.py` | `verdict`: the one place `public_upload_allowed` reads true, and `held_rows` for `findings` |
| `narrate/video/look.py`, `avatar.py`, `avatar_manifest.py` | the `look` external: a clip per voice take, bound by digest |
| `narrate/video/deliver.py` | a Campaign job's listening and lip sync read `not_applicable`, and `campaign_rows` names what no gate read |
| `narrate/video/admit.py` | a Campaign job's overlay is a look, no voice reads under a client consent, and it lists no listening or lip sync |
| `narrate/video/job.py`, `bundle.py`, `cli.py`, `render_stage.py` | the edition, `--look`, `campaign-verdict` and the render stage admitting `Campaign` |
| `narrate/dhall/Edition.dhall`, `Consent.dhall`, `check.py` | the edition and the `CampaignStandingRule` scope, which never grants a voice |
| `program/dags/narrated-video.json` | `look` in the avatar dispatch. `row.tasks_sha256` stays, and the file digest moves |

## Decisions in this draft

- `deliver_check` itself never says public for any edition. It holds neither the signed record nor the checks. A separate
  verdict also keeps every stage key where it was, and a client or internal report keeps its bytes.
- The binding stays #98's `rerun.json` row. A new field on the job would have moved every job's digest.
- A page in `exempt` refuses like a page in `unchecked`, because a bundle's exemption asked a person to read that page. A
  campaign deck has to be flat where the look sits. I read that as the bar, so such a cut routes to a fix.
- This repository holds no signing key. The caller verifies the campaign record's signature, and `resolution` reads
  `caller_checked`. `consents.json` still has to hold the grant the evidence names, unrevoked, so a withdrawal stops the
  next cut here too.
- `campaign-manifest` prints the render manifest before the checks run, because item 2.5's `manifest` check reads it. The
  verdict then takes all seven results and prints the same four fields.
- The look route binds clips made elsewhere. It does not draw one, because the live head and lip sync lanes are not landed.

## Review findings

An adversarial review of this draft (R-HOOK-CONVERGENCE-20261004 R-N13, Linear TIN-7788) planted each of these and saw the
failure before the fix.

| Fault | Fix |
| --- | --- |
| A failed `confidentiality` check gave stage `script`, so a fix author could rewrite disclosure-hold, client or health content until it passed | `campaign_confidentiality_refused`, a stop row. The signed record never covers that content |
| One state per check hid item 2.5's stop on a failed adult read, so it routed to a re-render | `stopped` state, `campaign_check_stopped`, a stop row |
| A voice's consent revoked, or a client consent recorded, after the cut still read public: the verdict ran no admit | `campaign_admit_refused`, from admit on the current records |
| `CampaignStandingRule` was refused as a voice scope only in `check.py`, so `narrate/policy.py` let it through at run time | `check_consent` refuses it with `consent_scope` |
| A probe printing `N/A` for a clip's count or rate raised `ValueError` in the stage | a `look_clip_invalid` problem |

## Open

| Point | Owner |
| --- | --- |
| The seven check names match item 2.5's draft `CAMPAIGN_CHECKS` as read today. Its refusal codes are not this verdict's | 2.5 |
| A bed still refuses here, with `campaign_operator_state_open` and `bed_acquisition_agent`. Agent-chosen beds need the licence record shape | 2.8 |
| The first real clip of the campaign's look: format, size and whether it is ProRes with alpha. A lane's output today is H.264 over a full frame, so a conversion step or a full-frame layout stays to build | look lane |
| Nothing measures whether a look's mouth follows the voice. The signed rule lifts the person, and no machine check stands in for lip sync | 2.5 |
| The campaign's dates, the Softproxy halt and the go pin are the caller's to check before it writes evidence | 3.3 |
| `file_sha256` and the blob of the DAG file move, so the row pin needs one re-pin at landing | 1.5 |
