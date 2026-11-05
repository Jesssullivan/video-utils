# Narrated video L5: first avatar render on kitpip 0.1.0 (2026-10-28)

Authority: SPR-49 and SPR-51 (TIN-7125 comments `339f944a` and `d7957dd4`).
NV-1 (TIN-7476 comment `9db389dc`) keeps the pin private. Receipt per
R-HOOK-CONVERGENCE-20261004 (R-N13). Owning issue: TIN-7476.

`narrated-video L5 render | narrate seat | video-utils main f449b5c0 | pin-check ok, one avatar render, digests below | lip-sync acceptance by the operator, L6 compose`

This receipt holds digests and ids only. It names no art, media, path, host or
URL.

## The pin

The private pin record now names the kitpip 0.1.0 release. Its `gate_state`
is `registered_hash_bound_not_accepted`.

| Item | Value |
| --- | --- |
| Private record SHA-256, before | `1cf1556d4a6b2d00cc402766d3e20671675047675507a45ee3aca5259393fcbb` |
| Private record SHA-256, after | `05fcc9c11c3f19d3cad6e8e4db19a8f9d82eaf20d94a18be10a8012490ef8984` |
| kitpip version | `0.1.0` |
| kitpip binary, x86_64-linux | SHA-256 `6e565eac5094fe94f355640a44ba7d24984b42c85a0c179e93762f8ed0f60f16`, 4431144 bytes |
| Default rig | `kitpip-v1` revision 2, SHA-256 `e970ef0d5b1dbeb90d8daa79200f70d195dc4f37825d228231a95915065e9d2d` |
| `just kitpip-pin-check` | `ok: true`, state `resolved` |

## The render

The job ran on the synthetic fixture workspace from `narrate video fixture`.
Its voice is a generated sine under the fixture consent, so no real voice,
script or picture entered the run. kitpip itself was the pinned release
binary, not the stub. The job came from `init --avatar --persona
fixture-persona`. Plan showed `avatar/seg-1` and `avatar_check/seg-1` as
`stale (upstream_stale)` before the run, not `kitpip_pin_pending`.

| Stage | Key | Content SHA-256 |
| --- | --- | --- |
| `script/seg-1` | `b50228abbd5dbf35` | `f2876d704b56a472f4f5e145eb466badf2d97e66348bcf24f660886df0a85162` |
| `base` | `91afcae26ffea845` | `cfed3986ec2dd4dcd4321e69f7ae1346be5e4954c2a30496ccd502797ed5a16a` |
| `voice/seg-1` | `76fbc739163271b4` | `4c586e56b41d5834ffcd86b958543aa5fb040494c3116a4e61359f62c5e35168` |
| `voice_qa/seg-1` | `7e3193f2b9042848` | `8a024ebc6264d62f7379913bf92baf998ccc406893dbecd87f8d6219274e64fa` |
| `avatar/seg-1` | `a94de985a7afa8c0` | `8eeee45894f6acbbcf9148a9eb0c98e3cffedf10b74ed6b344f59b3726275e26` |
| `place` | `7b0c0271f3104580` | `b56b6fe95c0b274b4655e7875758ef27bb26617187e6a1c01f3b9b1ce7e8bf2f` |
| `avatar_check/seg-1` | `3901405ed6e1a117` | `1da36919e4c59d42a3c31dedfd3c033ff7901d227008e623d990b9a0a0abe2c4` |
| `mix` | `fd138451ad401b96` | `0ef0e3d3965798034c3316617c6c7b95d942fa697aa828a79435aab271f9455a` |

`compose` stays `stale (no_run)` because L6 has not merged. `music` and
`handoff` are `not_selected`.

| Measurement | Value |
| --- | --- |
| `overlay/overlay.mov` | SHA-256 `c0d465463f5dc6658be8e493174680b1a22076e089ca56468f7c2209634dd173`, 41201755 bytes |
| `frames_sha256` | `5c56cc6298935fba434e36a06baf1e55ce6e29d9eb8c62700e3c4c8b9fa3bb31` |
| Frames | 180 at 30/1, 512 by 512 |
| `kitpip verify` | `labelled: true`. `show_badge` is false (KP-19) |
| `avatar_check` | `labelled: true`, frame digest equal to the avatar's |
| `narrate video verify` | `ok: true`, no problem in any of the 8 stages |
| States | render `local`, source checks `passed`, lip sync `pending_operator` |

## Repeat run

A second run into a fresh root gave the same avatar key, `overlay.mov` digest
and `frames_sha256`. The avatar content digest and the `avatar_check` key
differed. kitpip's `prosody.json` and overlay manifest bind the narrate
manifest's digest. That manifest carries the narrate run id, so it changes on
every voice run. The rendered frames do not.

## Evidence

All runs used `nix develop .#condense` under `env -i` inside `systemd-run
--user --scope -p MemoryMax=6G -p MemorySwapMax=0 nice -n 19`, in a worktree
at main `f449b5c0`. The kitpip binary was resolved by SHA-256 from a private
store through `KITPIP_BIN`.

## Open

- Lip-sync and listening acceptance are the operator's. This render is
  local and unaccepted.
- The render used the fixture voice. A render of a real narration waits on a
  job the operator names.
- Only the x86_64-linux binary is pinned. Darwin and aarch64 need a build on
  those systems.
