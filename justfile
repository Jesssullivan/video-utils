set shell := ["bash", "-euo", "pipefail", "-c"]
set dotenv-load := false

import 'just/workflow.just'
import 'just/bazel.just'
import 'just/take.just'
import 'just/condense.just'
import 'just/narrate-bench.just'
import 'just/narrate-dhall.just'
import 'just/narrate.just'

default:
    @just --list
