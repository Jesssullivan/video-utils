set shell := ["bash", "-euo", "pipefail", "-c"]
set dotenv-load := false

import 'just/workflow.just'
import 'just/bazel.just'

default:
    @just --list
