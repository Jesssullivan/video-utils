set shell := ["bash", "-euo", "pipefail", "-c"]
set dotenv-load := false

import 'just/workflow.just'

default:
    @just --list
