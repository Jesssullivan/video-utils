#!/usr/bin/env python3
"""Apply one hash-pinned authored capture profile through existing restoration."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import uuid

REPO = Path(__file__).resolve().parents[1]
ROOT = REPO
AUTHORING_SHA256 = "7d2820878826c87aabf2ab60b73c997b9d406b7f3ff8943d6012ed967444c355"
MAX_RECEIPT_BYTES = 64 * 1024
MAX_RESULT_BYTES = 16 * 1024
MAX_PROCESS_LOG_BYTES = 4 * 1024 * 1024
MAX_CLEANUP_SECONDS = 5.0
MAX_INSPECTION_SECONDS = 3.0
MIN_DIRECT_REAP_RESERVE_SECONDS = .25
CLI_ALARM_HANDLER = None
LAST_COMMITTED = None
LAST_COMMIT_CONTEXT = None
LAST_POSSIBLE_CANDIDATE = None
spec = importlib.util.spec_from_file_location("_application_capture", REPO / "scripts/capture_profile.py")
capture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(capture)
media = capture.media


class ApplyError(ValueError):
    def __init__(self, message, code="validation_failed"):
        super().__init__(message)
        self.code = code


class Deadline:
    def __init__(self, seconds):
        if isinstance(seconds, bool) or not isinstance(seconds, int) or not 1 <= seconds <= 600:
            raise ApplyError("timeout_seconds must be an integer between 1 and 600")
        self.seconds = seconds
        self.ends = time.monotonic() + seconds

    def check(self):
        if time.monotonic() >= self.ends:
            raise ApplyError("capture-profile application deadline exceeded", "deadline_exceeded")

    def remaining(self):
        self.check()
        return max(.001, self.ends - time.monotonic())


def fail(condition, message):
    if condition:
        raise ApplyError(message)


def obj(value, name):
    fail(not isinstance(value, dict), f"{name} must be an object")
    return value


def path(value, *, directory=False):
    return capture.safe_path(value, directory=directory)


def digest(file, deadline, bound, label):
    return capture.hash_file(file, deadline, bound, label)


def json_input(file, bound, deadline, label):
    return capture.read_json(file, bound, deadline, label)


def numeric(value, low, high, name):
    return capture.numeric(value, low, high, name)


def same_native(actual, expected, name):
    for key in ("sample_rate", "channels", "sample_count"):
        capture.integer(expected.get(key), 1, 192000 * 600, f"{name} {key}")
        fail(actual[key] != expected[key], f"{name} native {key} differs")


def validate(input_value, authoring_dir_value, receipt_sha256, deadline):
    """No subprocess launch; all caller paths and identities are checked here."""
    expected_receipt = capture.hex_digest(receipt_sha256, "receipt_sha256")
    source = path(input_value)
    run_root = path(ROOT / "artifacts/runs", directory=True)
    authored = path(authoring_dir_value, directory=True)
    fail(authored.parent.name != "capture-profiles", "authoring directory must be a capture-profiles child")
    parent = path(authored.parent.parent, directory=True)
    capture.underneath(parent, run_root)
    fail(parent == run_root, "parent must be a completed source run")
    receipt_path = path(authored / "receipt.json")
    receipt, actual_receipt = json_input(receipt_path, capture.MAX_RECEIPT_BYTES, deadline, "authoring receipt")
    fail(actual_receipt != expected_receipt, "authoring receipt SHA-256 differs from the pinned result")
    capture.integer(receipt.get("schema_version"), 1, 1, "authoring receipt schema_version")
    fail(receipt.get("tool") != "capture_profile" or receipt.get("status") != "authored_unrendered"
         or receipt.get("evidence_kind") != "source_bound_profile_authoring", "receipt is not an authored_unrendered capture profile")
    for key in ("dsp_performed", "audio_decoded", "learned_band_shape", "listening_accepted"):
        fail(receipt.get(key) is not False, f"authoring receipt {key} must remain false")
    fail(receipt.get("proposal_path") is not None, "an authoring proposal cannot be applied")
    profile_path = path(authored / "profile.json")
    fail(path(receipt.get("profile_path")) != profile_path, "profile path differs from this authored directory")
    profile, profile_hash = json_input(profile_path, capture.MAX_PROFILE_BYTES, deadline, "authored profile")
    fail(capture.hex_digest(receipt.get("profile_sha256"), "profile_sha256") != profile_hash,
         "authored profile bytes changed")
    manifest_path = path(parent / "manifest.json")
    pcm_path = path(parent / "source.wav")
    manifest, manifest_hash = json_input(manifest_path, capture.MAX_MANIFEST_BYTES, deadline, "parent manifest")
    source_hash = digest(source, deadline, capture.MAX_SOURCE_BYTES, "original source")
    pcm_hash = digest(pcm_path, deadline, capture.MAX_PCM_BYTES, "parent source PCM")
    baseline = obj(receipt.get("baseline"), "authoring baseline")
    receipt_source = obj(receipt.get("source"), "authoring source")
    manifest_source = obj(manifest.get("source"), "parent source")
    timeline = obj(manifest.get("timeline"), "parent timeline")
    outputs = obj(manifest.get("outputs"), "parent outputs")
    output_hashes = obj(manifest.get("output_sha256"), "parent output hashes")
    capture.integer(manifest.get("schema_version"), 1, 1, "parent schema_version")
    fail(path(receipt_source.get("path")) != source or path(manifest_source.get("path")) != source,
         "original input is not the exact authored source path")
    fail(receipt_source.get("sha256") != source_hash or manifest_source.get("sha256") != source_hash,
         "current original source hash differs")
    fail(path(baseline.get("run_dir"), directory=True) != parent or path(baseline.get("pcm_path")) != pcm_path,
         "receipt refers to another parent run or PCM")
    fail(baseline.get("manifest_sha256") != manifest_hash or baseline.get("pcm_sha256") != pcm_hash
         or outputs.get("source") != "source.wav" or output_hashes.get("source.wav") != pcm_hash,
         "parent manifest or PCM identity differs")
    fail(timeline.get("no_time_stretch") is not True, "verified no-time-stretch native mapping is required")
    origin = numeric(timeline.get("audio_start_seconds"), -86400, 86400, "verified audio origin")
    native = capture.native_pcm(pcm_path, deadline)
    same_native(native, obj(manifest.get("pcm"), "parent PCM"), "parent PCM")
    same_native(native, obj(baseline.get("pcm"), "receipt PCM"), "receipt PCM")
    fail(native["sample_count"] > native["sample_rate"] * 300, "source audio exceeds 300 seconds")
    probe = manifest_source.get("probe")
    if probe is not None:
        probe = obj(probe, "parent probe")
        format_duration = obj(probe.get("format"), "parent format").get("duration")
        if format_duration is not None:
            numeric(format_duration, .000001, 300, "parent container duration")
    cap = obj(receipt.get("capture"), "authored capture")
    samples = cap.get("native_samples")
    fail(not isinstance(samples, list) or len(samples) != 2, "capture requires exact native sample bounds")
    for sample in samples:
        capture.integer(sample, 0, native["sample_count"], "capture sample")
    rate = native["sample_rate"]
    fail(not 0 <= samples[0] < samples[1] <= native["sample_count"]
         or not (rate + 9) // 10 <= samples[1] - samples[0] <= rate * 10,
         "capture sample interval is outside inclusive native bounds")
    requested = cap.get("requested_seconds")
    fail(not isinstance(requested, list) or len(requested) != 2, "requested capture seconds are unavailable")
    for value in requested:
        numeric(value, 0, 300, "requested capture seconds")
    fail([round(value * rate) for value in requested] != samples, "requested capture seconds move native bounds")
    profile_seconds = cap.get("profile_seconds")
    fail(not isinstance(profile_seconds, list) or len(profile_seconds) != 2, "profile encoding bounds are unavailable")
    for value in profile_seconds:
        numeric(value, 0, 300, "profile capture seconds")
    fail([round(value * rate) for value in profile_seconds] != samples
         or profile_seconds[1] > native["sample_count"] / rate
         or not .1 <= profile_seconds[1] - profile_seconds[0] <= 10,
         "profile seconds do not preserve native capture bounds")
    fail(cap.get("time_axis") != "decoded_source_audio_samples" or cap.get("noise_only_verified") is not False
         or cap.get("audio_origin_seconds") != origin
         or cap.get("source_media_span_seconds") != [origin + sample / rate for sample in samples],
         "capture uncertainty or verified time axis differs")
    review_receipt = obj(receipt.get("review"), "review receipt")
    review_path = path(review_receipt.get("path"))
    capture.underneath(review_path, parent)
    review, review_hash = json_input(review_path, capture.MAX_REVIEW_BYTES, deadline, "capture review")
    fail(review_receipt.get("sha256") != review_hash or review_receipt.get("assertions") != review
         or review_receipt.get("identity_authenticated") is not False, "capture review bytes/assertion scope differs")
    capture.validate_review(review, source_hash, manifest_hash, pcm_hash, samples, rate)
    fail(review.get("authorization_scope") != "experimental_capture_render"
         or review.get("review_status") == "rejected_contaminated"
         or any(review.get(key) == "reviewed_present" for key in ("music_status", "click_status")),
         "existing scoped capture-render authorization is unavailable or selection is rejected")
    settings = obj(receipt.get("settings"), "authoring settings")
    required_controls = set(capture.CONTROL_LIMITS)
    fail(set(settings) - (required_controls | {"peaking_eq", "compressor"}) or not required_controls <= set(settings),
         "authoring settings contain missing or unsupported controls")
    for key, limits in capture.CONTROL_LIMITS.items():
        numeric(settings[key], *limits, key)
    capture.integer(settings["gain_smooth"], 0, 50, "gain_smooth")
    settings_hash = hashlib.sha256(capture.json_bytes(settings, capture.MAX_PROFILE_BYTES)).hexdigest()
    fail(receipt.get("settings_sha256") != settings_hash, "settings digest differs")
    profile_required = required_controls | {"schema_version", "name", "description", "denoise",
        "preserve_low_fundamental_hz", "noise_capture_seconds", "noise_capture_authorized",
        "noise_capture_source_sha256", "noise_capture_review"}
    fail(set(profile) != profile_required | (set(settings) & {"peaking_eq", "compressor"}),
         "profile is not the closed authored schema")
    fail(any(profile[key] != value for key, value in settings.items()), "profile controls differ from authored settings")
    capture.integer(profile.get("schema_version"), 1, 1, "profile schema_version")
    fail(profile.get("denoise") is not True or profile.get("preserve_low_fundamental_hz") != 32
         or profile.get("noise_capture_authorized") is not True
         or profile.get("noise_capture_source_sha256") != source_hash
         or profile.get("noise_capture_seconds") != profile_seconds, "profile lacks exact source-bound captured settings")
    validated = media.load_profile(profile_path)
    planned_stages = media.post_denoise_filters(settings, rate)
    fail(validated != profile or receipt.get("planned_post_denoise_stages") != planned_stages,
         "profile or planned stage validation differs")
    contexts = obj(receipt.get("context"), "authoring context")
    fail(set(contexts) != {"instrument.json", "capture-context.json"}, "registered context identities are unavailable")
    bindings = [(source, source_hash, capture.MAX_SOURCE_BYTES, "original source"),
                (manifest_path, manifest_hash, capture.MAX_MANIFEST_BYTES, "parent manifest"),
                (pcm_path, pcm_hash, capture.MAX_PCM_BYTES, "parent PCM"),
                (review_path, review_hash, capture.MAX_REVIEW_BYTES, "capture review"),
                (receipt_path, actual_receipt, capture.MAX_RECEIPT_BYTES, "authoring receipt"),
                (profile_path, profile_hash, capture.MAX_PROFILE_BYTES, "authored profile")]
    for name, context in contexts.items():
        context = obj(context, f"{name} context")
        context_path = path(ROOT / "program" / name)
        fail(path(context.get("path")) != context_path, "context path differs from this repository")
        current, current_hash = json_input(context_path, capture.MAX_CONTEXT_BYTES, deadline, name)
        fail(context.get("sha256") != current_hash or context.get("snapshot") != current, "current instrument/capture context differs")
        bindings.append((context_path, current_hash, capture.MAX_CONTEXT_BYTES, name))
    producer = obj(receipt.get("producer"), "authoring producer")
    authoring_file, validator_file = path(REPO / "scripts/capture_profile.py"), path(REPO / "scripts/media.py")
    authoring_hash = digest(authoring_file, deadline, capture.MAX_MANIFEST_BYTES, "frozen authoring worker")
    validator_hash = digest(validator_file, deadline, capture.MAX_MANIFEST_BYTES, "frozen media validator")
    fail(authoring_hash != AUTHORING_SHA256 or producer.get("worker_sha256") != authoring_hash
         or producer.get("validator_sha256") != validator_hash, "authoring/media producer source differs from the qualified identity")
    bindings += [(authoring_file, authoring_hash, capture.MAX_MANIFEST_BYTES, "frozen authoring worker"),
                 (validator_file, validator_hash, capture.MAX_MANIFEST_BYTES, "frozen media worker")]
    worker_file = path(Path(__file__).resolve())
    worker_hash = digest(worker_file, deadline, capture.MAX_MANIFEST_BYTES, "application worker")
    bindings.append((worker_file, worker_hash, capture.MAX_MANIFEST_BYTES, "application worker"))
    return {"source": source, "parent": parent, "authored": authored, "receipt": receipt,
            "receipt_hash": actual_receipt, "profile": profile, "profile_path": profile_path,
            "profile_hash": profile_hash, "settings_hash": settings_hash, "native": native,
            "capture": cap, "origin": origin, "bindings": bindings, "worker_hash": worker_hash,
            "validator_hash": validator_hash, "has_post_stages": bool(planned_stages)}


def recheck(state, deadline):
    for file, expected, bound, label in state["bindings"]:
        fail(digest(file, deadline, bound, label) != expected, f"{label} changed before publication")


def live_group_members(pgid, *, timeout=MAX_INSPECTION_SECONDS):
    """Inspect the recorded group and recheck each runnable member's session."""
    inspection_timeout = min(MAX_INSPECTION_SECONDS, timeout)
    fail(inspection_timeout <= 0, "owned process-group inspection budget exhausted")
    inspection_end = time.monotonic() + inspection_timeout
    result = subprocess.run(["/bin/ps", "-ax", "-o", "pid=,pgid=,stat="],
                            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, timeout=inspection_timeout, check=False)
    fail(result.returncode != 0 or len(result.stdout.encode()) > MAX_PROCESS_LOG_BYTES,
         "owned process-group inspection failed")
    members = []
    for line in result.stdout.splitlines():
        fail(time.monotonic() >= inspection_end, "owned process-group inspection budget exhausted")
        fields = line.split()
        if len(fields) < 3 or not fields[0].isdigit() or not fields[1].isdigit():
            continue
        pid, group = int(fields[0]), int(fields[1])
        if group != pgid or fields[2].startswith("Z"):
            continue
        try:
            fail(os.getpgid(pid) != pgid or os.getsid(pid) != pgid,
                 "live group member differs from the worker-created session")
        except ProcessLookupError:
            continue
        members.append(pid)
    return members


@contextmanager
def protect_owned_cleanup():
    """An owned outer alarm must not interrupt child termination/reaping."""
    owned = CLI_ALARM_HANDLER is not None and signal.getsignal(signal.SIGALRM) is CLI_ALARM_HANDLER
    prior = signal.getitimer(signal.ITIMER_REAL) if owned else (0., 0.)
    started = time.monotonic()
    if owned:
        signal.setitimer(signal.ITIMER_REAL, 0)
    try:
        yield
    finally:
        if owned and prior[0] > 0 and LAST_COMMITTED is None and LAST_POSSIBLE_CANDIDATE is None:
            remaining = prior[0] - (time.monotonic() - started)
            # Expiry is already handled by the stage/whole-job deadline; do
            # not inject a second alarm into the exception/reporting path.
            if remaining > 0:
                signal.setitimer(signal.ITIMER_REAL, remaining, prior[1])


def cleanup_remaining(ends):
    remaining = ends - time.monotonic()
    if remaining <= 0:
        raise ApplyError("owned process cleanup budget exhausted", "cleanup_failed")
    return remaining


def observe_owned_group(pgid, ends, observations):
    """Retry only a timed-out observation, never ownership mismatches."""
    for attempt in (1, 2):
        remaining = cleanup_remaining(ends) - MIN_DIRECT_REAP_RESERVE_SECONDS
        if remaining <= 0:
            raise ApplyError("owned group observation exhausted its budget with direct-reap reserve", "cleanup_failed")
        inspection_timeout = min(MAX_INSPECTION_SECONDS, remaining)
        try:
            members = live_group_members(pgid, timeout=inspection_timeout)
        except subprocess.TimeoutExpired as exc:
            observations.append({"attempt": attempt, "timeout_seconds": inspection_timeout,
                                 "error": str(exc)[:500], "result": "observation_timed_out"})
            if attempt == 2:
                raise
        else:
            if attempt == 2:
                observations[-1]["result"] = "timeout_then_retry_observed"
            return members


def cleanup_verified_group(process, pgid, reason, events, ends, observations):
    with protect_owned_cleanup():
        leader_terminated_before_observation = process.poll() is not None
        members = observe_owned_group(pgid, ends, observations)
        event = {"actor": "apply_capture_profile", "leader_pid": process.pid, "pgid": pgid,
                 "session_id": pgid, "reason": reason, "ruling": "R-N11/R-N12",
                 "prior_state": {"leader_returncode": process.poll(), "live_members": members[:32]},
                 "signals": [], "cleanup_seconds_max": MAX_CLEANUP_SECONDS,
                 "inspection_retries": observations}
        events.append(event)
        if members:
            # The members above have live PGID and SID equal to the fresh
            # session created specifically for this Popen object.
            try:
                os.killpg(pgid, signal.SIGTERM)
                event["signals"].append("SIGTERM")
            except ProcessLookupError:
                pass
            limit = time.monotonic() + .15
            while time.monotonic() < min(limit, ends) and observe_owned_group(pgid, ends, observations):
                time.sleep(min(.015, max(0, ends - time.monotonic())))
            remaining = observe_owned_group(pgid, ends, observations)
            if remaining:
                try:
                    os.killpg(pgid, signal.SIGKILL)
                    event["signals"].append("SIGKILL")
                except ProcessLookupError:
                    pass
        try:
            process.wait(timeout=cleanup_remaining(ends))
        except subprocess.TimeoutExpired as exc:
            raise ApplyError("owned process leader could not be reaped", "cleanup_failed") from exc
        if not members and leader_terminated_before_observation:
            # The initial observation follows the leader's terminal status;
            # waiting on this exact Popen confirms it can no longer fork.
            # Empty group observation can therefore be reused, without a
            # redundant scan or a weaker descendant-absence assertion.
            remaining = []
            event["verification_method"] = "empty_group_after_leader_terminated_and_direct_wait"
        else:
            remaining = observe_owned_group(pgid, ends, observations)
            while remaining and time.monotonic() < ends:
                time.sleep(min(.015, max(0, ends - time.monotonic())))
                remaining = observe_owned_group(pgid, ends, observations)
            event["verification_method"] = "post_wait_live_same_session_group_inspection"
        event["result"] = "leader_reaped_no_runnable_same_session_group_members" if not remaining else "cleanup_incomplete"
        fail(bool(remaining), "owned process-group cleanup remained incomplete")


def cleanup_owned_group(process, pgid, reason, events):
    ends = time.monotonic() + MAX_CLEANUP_SECONDS
    observations = []
    try:
        cleanup_verified_group(process, pgid, reason, events, ends, observations)
    except BaseException as exc:
        # Inspection can fail. Popen still owns its direct unreaped child;
        # always terminate/reap it, without guessing an unrelated session.
        with protect_owned_cleanup():
            prior = process.poll()
            signaled_group = False
            signal_errors = []
            event = {"actor": "apply_capture_profile", "leader_pid": process.pid, "pgid": pgid,
                "session_id": pgid, "reason": reason, "ruling": "R-N11/R-N12",
                "prior_state": {"leader_returncode": prior, "live_members": None,
                                "inspection_failure": str(exc)[:500]},
                "signals": [], "signal_errors": signal_errors, "cleanup_seconds_max": MAX_CLEANUP_SECONDS,
                "inspection_retries": observations[-8:], "result": "direct_child_reap_pending"}
            events.append(event)
            try:
                if prior is None:
                    try:
                        if os.getpgid(process.pid) == pgid and os.getsid(process.pid) == pgid:
                            os.killpg(pgid, signal.SIGKILL)
                            signaled_group = True
                            event["signals"].append("SIGKILL_owned_session")
                    except ProcessLookupError:
                        pass
                    except OSError as signal_error:
                        signal_errors.append(str(signal_error)[:500])
                    finally:
                        if process.poll() is None:
                            try:
                                process.kill()
                                event["signals"].append("direct_child_kill_if_running")
                            except ProcessLookupError:
                                pass
                            except OSError as signal_error:
                                signal_errors.append(str(signal_error)[:500])
            finally:
                try:
                    process.wait(timeout=max(0., ends - time.monotonic()))
                except subprocess.TimeoutExpired as wait_error:
                    event["result"] = "direct_child_reap_timeout_descendant_absence_unverified"
                    error = ApplyError("owned process inspection failed and direct child could not be reaped", "cleanup_failed")
                    error.process_ownership = list(events)
                    raise error from wait_error
            event["result"] = "direct_child_reaped_descendant_absence_unverified"
        error = ApplyError("owned process inspection/cleanup failed; direct child reaped, descendant absence unverified", "cleanup_failed")
        error.process_ownership = list(events)
        raise error from exc


def run_owned(command, *, deadline, timeout=600, events=None):
    """Run existing media arguments in an owned session with bounded logs."""
    deadline.check()
    events = [] if events is None else events
    fail(not isinstance(command, list) or not command or any(not isinstance(arg, str) for arg in command),
         "media subprocess requires a fixed argument vector")
    fail(not Path("/bin/ps").is_file(), "owned process inspection is unavailable")
    fail(len(events) >= 128, "media subprocess count exceeds the application bound")
    # Reserve cleanup time within the job budget. The CLI also protects the
    # bounded cleanup from its one-shot alarm if an exceptional interruption
    # arrives during a subprocess; no external timer is disabled.
    remaining = deadline.remaining()
    reserve = min(MAX_CLEANUP_SECONDS, remaining / 2)
    stage_end = min(time.monotonic() + timeout, deadline.ends - reserve)
    fail(stage_end <= time.monotonic(), "no media subprocess time remains")
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=stdout,
                                   stderr=stderr, start_new_session=True, close_fds=True)
        pgid = process.pid
        reason = "stage_finished"
        try:
            # setsid is performed before exec by start_new_session. If the
            # leader already exited, live_group_members verifies survivors.
            if process.poll() is None:
                try:
                    fail(os.getpgid(process.pid) != pgid or os.getsid(process.pid) != pgid,
                         "media process did not enter its owned session")
                except ProcessLookupError:
                    pass
            while process.poll() is None:
                if time.monotonic() >= stage_end:
                    reason = "stage_deadline_exceeded"
                    raise ApplyError("media subprocess deadline exceeded", "deadline_exceeded")
                if any(os.fstat(handle.fileno()).st_size > MAX_PROCESS_LOG_BYTES for handle in (stdout, stderr)):
                    reason = "stage_log_limit_exceeded"
                    raise ApplyError("media subprocess output exceeded its byte bound", "resource_limit")
                time.sleep(min(.025, max(.001, stage_end - time.monotonic())))
        except BaseException as exc:
            if reason == "stage_finished":
                reason = "stage_interrupted"
            exc.process_ownership = events
            raise
        finally:
            cleanup_owned_group(process, pgid, reason, events)
        deadline.check()
        fail(any(os.fstat(handle.fileno()).st_size > MAX_PROCESS_LOG_BYTES for handle in (stdout, stderr)),
             "media subprocess output exceeded its byte bound")
        stdout.seek(0)
        stderr.seek(0)
        result = subprocess.CompletedProcess(command, process.returncode,
            stdout.read(MAX_PROCESS_LOG_BYTES + 1).decode("utf-8", errors="replace"),
            stderr.read(MAX_PROCESS_LOG_BYTES + 1).decode("utf-8", errors="replace"))
        if result.returncode:
            error = media.MediaError(f"{Path(command[0]).name} failed ({result.returncode}): {result.stderr[-2500:]}")
            error.process_ownership = list(events)
            raise error
        return result


@contextmanager
def private_media(workspace, deadline, events):
    old_root, old_run = media.ROOT, media.run
    fail(media.THREADS != "2", "qualified media worker must use two threads")
    def bounded_run(command, timeout=600):
        deadline.check()
        result = run_owned(command, deadline=deadline, timeout=timeout, events=events)
        deadline.check()
        return result
    media.ROOT, media.run = workspace, bounded_run
    try:
        yield
    finally:
        media.ROOT, media.run = old_root, old_run


def verify_render(manifest, state, workspace, deadline):
    manifest = obj(manifest, "rendered manifest")
    capture.integer(manifest.get("schema_version"), 1, 1, "render schema_version")
    fail(manifest.get("status") != "rendered_unreviewed", "render must remain unreviewed")
    directory = path(manifest.get("run_dir"), directory=True)
    capture.underneath(directory, workspace / "artifacts/runs")
    fail(directory.parent != workspace / "artifacts/runs" or manifest.get("run_id") != directory.name,
         "media worker returned an unexpected run directory")
    stored, unused_hash = json_input(path(directory / "manifest.json"), capture.MAX_MANIFEST_BYTES, deadline, "render manifest")
    fail(stored != manifest, "render manifest file differs from returned metadata")
    source = obj(manifest.get("source"), "rendered source")
    fail(path(source.get("path")) != state["source"] or source.get("sha256") != state["receipt"]["source"]["sha256"],
         "rendered source identity differs")
    fail(manifest.get("profile") != state["profile"] or manifest.get("threads") != 2,
         "rendered profile or thread bound differs")
    native = obj(manifest.get("pcm"), "rendered PCM")
    same_native(state["native"], native, "rendered PCM")
    timeline = obj(manifest.get("timeline"), "render timeline")
    fail(timeline.get("no_time_stretch") is not True or timeline.get("audio_start_seconds") != state["origin"],
         "render changed verified native time axis")
    noise = obj(manifest.get("noise_capture"), "rendered capture")
    fail(noise.get("source_sha256") != state["receipt"]["source"]["sha256"]
         or noise.get("selected_samples") != state["capture"]["native_samples"]
         or noise.get("applies_to_original_start") is not True
         or noise.get("source_axis_sample_count_preserved") is not True
         or noise.get("noise_only_verified_by_worker") is not False, "captured processing provenance differs")
    latency = obj(obj(manifest.get("dsp_latency"), "DSP latency").get("denoise"), "denoise latency")
    fail(latency.get("status") != "measured_and_compensated" or latency.get("remaining_bulk_delay_samples") != 0,
         "calibrated denoiser delay compensation is unavailable")
    capture.integer(latency.get("delay_samples"), 0, state["native"]["sample_rate"], "denoiser delay")
    expected = {"source": "source.wav", "denoised": "denoised.wav", "baseline": "baseline.wav",
                "cleaned": "cleaned.wav", "residue": "residue.wav"}
    if state["has_post_stages"]:
        expected["processed"] = "processed.wav"
    fail(manifest.get("outputs") != expected, "rendered artifact roles differ from the selected stages")
    hashes = obj(manifest.get("output_sha256"), "render output hashes")
    fail(set(hashes) != set(expected.values()), "render output identities are incomplete")
    for name in expected.values():
        file = path(directory / name)
        fail(digest(file, deadline, capture.MAX_PCM_BYTES, name) != hashes[name], "render output bytes differ")
        same_native(capture.native_pcm(file, deadline), state["native"], name)
    return directory


def verify_export(directory, outcome, manifest, state, deadline):
    outcome = obj(outcome, "export outcome")
    stored, unused_hash = json_input(path(directory / "export/outcome.json"), capture.MAX_MANIFEST_BYTES, deadline, "export outcome")
    fail(stored != outcome, "export outcome bytes differ from returned metadata")
    capture.integer(outcome.get("schema_version"), 1, 1, "export schema_version")
    fail(outcome.get("status") != "exported_unreviewed" or outcome.get("listening_accepted") is not False
         or outcome.get("source_sha256") != state["receipt"]["source"]["sha256"]
         or path(outcome.get("run_dir"), directory=True) != directory
         or path(outcome.get("audio_master")) != path(directory / "cleaned.wav"), "export identity or unreviewed scope differs")
    probe = obj(obj(manifest["source"], "render source").get("probe"), "render probe")
    video_source = probe.get("video")
    hashes = obj(outcome.get("output_sha256"), "export output hashes")
    if video_source is None:
        fail(outcome.get("video") is not None or hashes != {}, "audio-only export unexpectedly contains video")
    else:
        obj(video_source, "source video")
        video = path(directory / "export/cleaned-video.mov")
        fail(path(outcome.get("video")) != video or set(hashes) != {"cleaned-video.mov"}
             or digest(video, deadline, capture.MAX_SOURCE_BYTES, "exported video") != hashes["cleaned-video.mov"],
             "video export identity differs")
        verification = obj(outcome.get("verification"), "video verification")
        for key in ("source_hash_verified", "video_frame_count_preserved", "relative_audio_video_start_verified",
                    "dsp_latency_compensation_recorded", "final_true_peak_within_target"):
            fail(verification.get(key) is not True, f"video export {key} is unavailable")
        fail(verification.get("physical_audio_video_sync_verified") is not False,
             "video export must retain physical-sync uncertainty")
    return outcome


def publish_directory(staging, final):
    fail(final.exists() or final.is_symlink(), "application run already exists")
    staging.rename(final)


def preserve_failure(state, events, exc, committed_candidate=None, possible_candidate=None):
    """Keep bounded failure/signal evidence outside discarded audio staging."""
    parent = ROOT / "artifacts/application-failures"
    fail(parent.is_symlink(), "failure receipt parent cannot be a symlink")
    parent.mkdir(mode=0o700, exist_ok=True)
    path(parent, directory=True)
    name = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex
    final = parent / name
    staging = Path(tempfile.mkdtemp(prefix=".failure-staging-", dir=parent))
    try:
        data = {"schema_version": 1, "tool": "apply_capture_profile",
                "status": ("failed_reporting_committed_candidate_retained" if committed_candidate else
                           "publication_outcome_unknown" if possible_candidate else "failed_no_candidate_published"),
                "evidence_kind": "source_bound_capture_profile_application_failure",
                "ruling": "R-N11/R-N12/R-N13", "source": state["receipt"]["source"],
                "authoring_receipt_sha256": state["receipt_hash"], "profile_sha256": state["profile_hash"],
                "error": {"code": getattr(exc, "code", "processing_failed"), "message": str(exc)[:1000]},
                "owned_subprocesses": events, "listening_accepted": False, "master_adopted": False,
                "candidate_publication": ("committed_unreviewed" if committed_candidate else
                                          "unknown_after_publish_attempt" if possible_candidate else "not_committed"),
                "committed_candidate": committed_candidate,
                "possible_candidate": recovery_selectors(possible_candidate),
                "result": ("immutable committed candidate retained; private workspace discarded; no current-master replacement"
                           if committed_candidate else
                           "publication could not be observed; inspect prepared candidate selectors; no current-master replacement"
                           if possible_candidate else "owned private audio staging discarded; no success candidate or current-master replacement")}
        raw = capture.json_bytes(data, MAX_RECEIPT_BYTES)
        (staging / "receipt.json").write_bytes(raw)
        publish_directory(staging, final)
        return str(final / "receipt.json"), hashlib.sha256(raw).hexdigest()
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)


def apply(input_value, authoring_dir_value, receipt_sha256, *, timeout_seconds=600):
    global LAST_COMMITTED, LAST_COMMIT_CONTEXT, LAST_POSSIBLE_CANDIDATE
    LAST_COMMITTED = None
    LAST_COMMIT_CONTEXT = None
    LAST_POSSIBLE_CANDIDATE = None
    workspace = None
    state = None
    process_events = []
    try:
        deadline = Deadline(timeout_seconds)
        state = validate(input_value, authoring_dir_value, receipt_sha256, deadline)
        recheck(state, deadline)
        artifacts = path(ROOT / "artifacts", directory=True)
        workspace = Path(tempfile.mkdtemp(prefix=".capture-apply-", dir=artifacts))
        snapshot = workspace / "profile.json"
        snapshot.write_bytes(state["profile_path"].read_bytes())
        fail(digest(snapshot, deadline, capture.MAX_PROFILE_BYTES, "profile snapshot") != state["profile_hash"],
             "profile changed while snapshotting")
        with private_media(workspace, deadline, process_events):
            manifest = media.clean(state["source"], snapshot)
            directory = verify_render(manifest, state, workspace, deadline)
            outcome = media.export(directory)
            verify_export(directory, outcome, manifest, state, deadline)
            # Export must not change the PCM master or other stage files.
            verify_render(manifest, state, workspace, deadline)
        recheck(state, deadline)
        final = path(ROOT / "artifacts/runs", directory=True) / directory.name
        fail(final.exists() or final.is_symlink(), "application output would reuse an existing run")
        # History commands/probe filenames retain their actual staging paths;
        # only published artifact selectors are rewritten to the final run.
        manifest["run_dir"] = str(final)
        manifest["capture_profile_application"] = {"authoring_dir": str(state["authored"]),
            "authoring_receipt_sha256": state["receipt_hash"], "profile_sha256": state["profile_hash"],
            "receipt": "application-receipt.json", "listening_accepted": False}
        outcome["run_dir"] = str(final)
        outcome["audio_master"] = str(final / "cleaned.wav")
        if outcome["video"] is not None:
            outcome["video"] = str(final / "export/cleaned-video.mov")
        (directory / "manifest.json").write_bytes(capture.json_bytes(manifest, capture.MAX_MANIFEST_BYTES))
        (directory / "export/outcome.json").write_bytes(capture.json_bytes(outcome, capture.MAX_MANIFEST_BYTES))
        shutil.copyfile(snapshot, directory / "applied-profile.json")
        manifest_hash = digest(directory / "manifest.json", deadline, capture.MAX_MANIFEST_BYTES, "published manifest")
        outcome_hash = digest(directory / "export/outcome.json", deadline, capture.MAX_MANIFEST_BYTES, "published outcome")
        receipt = {"schema_version": 1, "tool": "apply_capture_profile", "status": "rendered_unreviewed",
            "evidence_kind": "source_bound_capture_profile_application", "created_utc": datetime.now(timezone.utc).isoformat(),
            "run_dir": str(final), "source": state["receipt"]["source"], "parent": state["receipt"]["baseline"],
            "authoring": {"directory": str(state["authored"]), "receipt_sha256": state["receipt_hash"],
                          "profile_sha256": state["profile_hash"], "settings_sha256": state["settings_hash"],
                          "review": state["receipt"]["review"], "context": state["receipt"]["context"]},
            "capture": state["capture"], "native_pcm": state["native"],
            "producer": {"application_worker_sha256": state["worker_hash"], "authoring_worker_sha256": AUTHORING_SHA256,
                         "media_worker_sha256": state["validator_hash"], "python_version": sys.version.split()[0],
                         "identity_scope": "current local source-file hashes observed/rechecked, not attestation"},
            "outputs": {"manifest_sha256": manifest_hash, "export_outcome_sha256": outcome_hash,
                        "audio_sha256": manifest["output_sha256"], "video_sha256": outcome["output_sha256"],
                        "applied_profile_sha256": state["profile_hash"]},
            "bounds": {"timeout_seconds": timeout_seconds, "source_duration_seconds_max": 300, "threads": 2,
                       "exceptional_cleanup_seconds_max": MAX_CLEANUP_SECONDS,
                       "process_inspection_seconds_max": MAX_INSPECTION_SECONDS,
                       "process_observation_attempts_max": 2,
                       "direct_reap_reserve_seconds": MIN_DIRECT_REAP_RESERVE_SECONDS},
            "processing": "existing media.clean and media.export; no alternate DSP or caller filter controls",
            "owned_subprocesses": process_events,
            "dsp_performed": True, "listening_accepted": False, "master_adopted": False,
            "warnings": [*state["receipt"]["warnings"],
                "Native mapping and export identity do not establish isolated guitar/fan components or good tone.",
                "No current master/latest pointer changed; this separate candidate requires comparative listening.",
                "Historical command and probe paths describe private staging execution; published selectors identify this run."]}
        raw_receipt = capture.json_bytes(receipt, MAX_RECEIPT_BYTES)
        (directory / "application-receipt.json").write_bytes(raw_receipt)
        recheck(state, deadline)
        deadline.check()
        summary = {"schema_version": 1, "tool": "apply_capture_profile", "status": "rendered_unreviewed",
            "evidence_kind": "source_bound_capture_profile_application", "run_dir": str(final),
            "source_sha256": state["receipt"]["source"]["sha256"], "profile_sha256": state["profile_hash"],
            "authoring_receipt_sha256": state["receipt_hash"], "manifest_path": str(final / "manifest.json"),
            "manifest_sha256": manifest_hash, "receipt_path": str(final / "application-receipt.json"),
            "receipt_sha256": hashlib.sha256(raw_receipt).hexdigest(),
            "capture": {key: state["capture"][key] for key in ("requested_seconds", "profile_seconds", "native_samples", "source_media_span_seconds")},
            "export": {"status": outcome["status"], "audio_master": outcome["audio_master"], "video": outcome["video"],
                       "outcome_path": str(final / "export/outcome.json"), "outcome_sha256": outcome_hash},
            "dsp_performed": True, "listening_accepted": False, "master_adopted": False}
        capture.json_bytes(summary, MAX_RESULT_BYTES)
        original_info = directory.stat()
        directory_identity = (original_info.st_dev, original_info.st_ino)
        # A one-shot owned deadline cannot split atomic publication from
        # recording its result. An exceptional publisher may rename and then
        # raise; device/inode identity proves this exact owned directory moved.
        with protect_owned_cleanup():
            try:
                publish_directory(directory, final)
            finally:
                prepared = json.loads(json.dumps(summary, allow_nan=False))
                try:
                    published_info = final.lstat()
                    if not final.is_symlink() and (published_info.st_dev, published_info.st_ino) == directory_identity:
                        # stat also observes the expected usable directory. A
                        # failed observation cannot be treated as no commit.
                        final.stat()
                        LAST_COMMITTED = prepared
                        LAST_COMMIT_CONTEXT = (state, process_events)
                except OSError:
                    pass
                if LAST_COMMITTED is None:
                    try:
                        retained = directory.stat()
                        not_moved = (retained.st_dev, retained.st_ino) == directory_identity
                    except OSError:
                        not_moved = False
                    if not not_moved:
                        LAST_POSSIBLE_CANDIDATE = prepared
                        LAST_COMMIT_CONTEXT = (state, process_events)
            fail(LAST_COMMITTED is None, "publication did not commit the exact owned candidate")
        return summary
    except (ApplyError, capture.CaptureError, media.MediaError, OSError, ValueError, KeyError, TypeError, OverflowError) as exc:
        error = exc if isinstance(exc, ApplyError) else ApplyError(str(exc), getattr(exc, "code", "validation_failed"))
        error.process_ownership = getattr(exc, "process_ownership", process_events)
        error.committed_candidate = LAST_COMMITTED
        error.possible_candidate = LAST_POSSIBLE_CANDIDATE
        if workspace is not None and state is not None:
            try:
                error.failure_receipt_path, error.failure_receipt_sha256 = preserve_failure(state, process_events, error, LAST_COMMITTED, LAST_POSSIBLE_CANDIDATE)
            except (ApplyError, capture.CaptureError, OSError) as failure_error:
                error.failure_receipt_error = str(failure_error)[:500]
        raise error from (exc if error is not exc else None)
    finally:
        if workspace is not None:
            shutil.rmtree(workspace, ignore_errors=True)


def recovery_selectors(committed):
    if committed is None:
        return None
    return {"schema_version": 1, "status": "rendered_unreviewed", "run_dir": committed["run_dir"],
            "source_sha256": committed["source_sha256"], "profile_sha256": committed["profile_sha256"],
            "authoring_receipt_sha256": committed["authoring_receipt_sha256"],
            "manifest": {"relative_path": "manifest.json", "sha256": committed["manifest_sha256"]},
            "receipt": {"relative_path": "application-receipt.json", "sha256": committed["receipt_sha256"]},
            "export_outcome": {"relative_path": "export/outcome.json", "sha256": committed["export"]["outcome_sha256"]},
            "listening_accepted": False, "master_adopted": False}


def error_diagnostic(exc, committed):
    possible = None if committed else getattr(exc, "possible_candidate", None)
    diagnostic = {"schema_version": 1, "tool": "apply_capture_profile",
        "status": ("committed_unreviewed_reporting_interrupted" if committed else
                   "publication_outcome_unknown" if possible else "error"),
        "evidence_kind": "source_bound_capture_profile_application",
        "error": {"code": getattr(exc, "code", "validation_failed"), "message": str(exc)[:1000]},
        "failure_receipt_path": getattr(exc, "failure_receipt_path", None),
        "failure_receipt_sha256": getattr(exc, "failure_receipt_sha256", None),
        "failure_receipt_error": getattr(exc, "failure_receipt_error", None),
        "owned_process_events": getattr(exc, "process_ownership", [])[-8:],
        "owned_process_events_omitted": False,
        "candidate_publication": ("committed_unreviewed" if committed else
                                  "unknown_after_publish_attempt" if possible else "not_committed"),
        "committed_candidate": recovery_selectors(committed),
        "possible_candidate": recovery_selectors(possible),
        "listening_accepted": False, "master_adopted": False}
    try:
        capture.json_bytes(diagnostic, MAX_RESULT_BYTES)
    except capture.CaptureError:
        # Full authority events remain in the bounded durable failure receipt.
        # Never truncate the actual committed run/manifest/receipt identities.
        diagnostic["owned_process_events"] = []
        diagnostic["owned_process_events_omitted"] = True
        diagnostic["error"]["message"] = diagnostic["error"]["message"][:256]
        diagnostic["failure_receipt_error"] = None
        capture.json_bytes(diagnostic, MAX_RESULT_BYTES)
    return diagnostic


def main(argv=None):
    global CLI_ALARM_HANDLER, LAST_COMMITTED, LAST_COMMIT_CONTEXT, LAST_POSSIBLE_CANDIDATE
    LAST_COMMITTED = None
    LAST_COMMIT_CONTEXT = None
    LAST_POSSIBLE_CANDIDATE = None
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input")
    parser.add_argument("--authoring-dir", required=True)
    parser.add_argument("--receipt-sha256", required=True)
    parser.add_argument("--timeout-seconds", type=int, default=600)
    args = parser.parse_args(argv)
    old_handler = None
    timer_owned = False
    try:
        capture.integer(args.timeout_seconds, 1, 600, "timeout_seconds")
        fail(signal.getitimer(signal.ITIMER_REAL) != (0.0, 0.0), "standalone application has an existing timer")
        old_handler = signal.getsignal(signal.SIGALRM)
        def expired(signum, frame):
            raise ApplyError("capture-profile application deadline exceeded", "deadline_exceeded")
        signal.signal(signal.SIGALRM, expired)
        CLI_ALARM_HANDLER = expired
        signal.setitimer(signal.ITIMER_REAL, args.timeout_seconds)
        timer_owned = True
        result = apply(args.input, args.authoring_dir, args.receipt_sha256, timeout_seconds=args.timeout_seconds)
        # Processing is committed. Console/transport reporting cannot turn it
        # into a precommit timeout or erase its immutable recovery selectors.
        if timer_owned:
            signal.setitimer(signal.ITIMER_REAL, 0)
        print(json.dumps(result, sort_keys=True, allow_nan=False))
        return 0
    except (ApplyError, capture.CaptureError, OSError) as exc:
        committed = getattr(exc, "committed_candidate", None) or LAST_COMMITTED
        possible = getattr(exc, "possible_candidate", None) or LAST_POSSIBLE_CANDIDATE
        exc.possible_candidate = possible
        if (committed or possible) and LAST_COMMIT_CONTEXT is not None:
            if timer_owned:
                signal.setitimer(signal.ITIMER_REAL, 0)
            if not getattr(exc, "failure_receipt_path", None):
                state, events = LAST_COMMIT_CONTEXT
                exc.process_ownership = events
                try:
                    exc.failure_receipt_path, exc.failure_receipt_sha256 = preserve_failure(state, events, exc, committed, possible)
                except (ApplyError, capture.CaptureError, OSError) as failure_error:
                    exc.failure_receipt_error = str(failure_error)[:500]
        print(json.dumps(error_diagnostic(exc, committed), sort_keys=True, allow_nan=False))
        return 2
    finally:
        if timer_owned:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, old_handler)
        CLI_ALARM_HANDLER = None


if __name__ == "__main__":
    sys.exit(main())
