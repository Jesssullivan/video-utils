"""Narrated video (docs/spec/NARRATED_VIDEO.md): one typed job, planned as a stage graph over a content-addressed store.

graph.py lists the 13 stages and plans a job; keys.py makes stage keys; store.py keeps stage directories under
artifacts/narrated/<job_id>/; admit.py is the read-only gate at the Plan point; job.py holds the defaults `init`
writes; kitpip.py resolves the pinned kitpip binary and runs the avatar stage. `python -m narrate video` is the CLI.
"""
