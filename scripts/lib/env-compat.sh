#!/bin/bash
# env-compat.sh — Dual-read shim for the agile-flow → Gemba Flow env-var rebrand.
#
# Reads the new GEMBAFLOW_* variable first, falls back to the deprecated
# AGILE_FLOW_* variable, and prints a one-line deprecation warning (once
# per shell session per variable) when the old name is the only one set.
#
# Usage:
#   source "$(dirname "${BASH_SOURCE[0]}")/lib/env-compat.sh"
#
#   # Read a variable with a default
#   account=$(gf_env GEMBAFLOW_WORKER_ACCOUNT AGILE_FLOW_WORKER_ACCOUNT va-worker)
#
#   # Read without a default (returns empty if neither set)
#   account=$(gf_env GEMBAFLOW_WORKER_ACCOUNT AGILE_FLOW_WORKER_ACCOUNT)
#
#   # Convenience wrappers for the three vars covered by Phase 2b
#   account=$(gf_worker_account)     # defaults to va-worker
#   account=$(gf_reviewer_account)   # defaults to va-reviewer
#   solo=$(gf_solo_mode)             # defaults to (empty)
#
# Deprecation policy: AGILE_FLOW_* will be removed in a future release.
# Migration: rename the variable in your shell rc / Codespaces secrets /
# devcontainer env from AGILE_FLOW_<NAME> to GEMBAFLOW_<NAME>.

# Track which old vars we have already warned about in this shell session
# so we do not spam the user with the same deprecation line repeatedly.
# Exported so subshells inherit the dedupe state.
export _GF_ENV_COMPAT_WARNED="${_GF_ENV_COMPAT_WARNED:-}"

# _gf_env_warn_once <old_var_name>
#
# Print the deprecation warning to stderr the first time we see <old_var_name>
# in this shell session. Subsequent calls for the same name are silent.
_gf_env_warn_once() {
    local old_name="$1"
    case ":${_GF_ENV_COMPAT_WARNED}:" in
        *":${old_name}:"*) return 0 ;;
    esac
    echo "WARNING: ${old_name} is deprecated; rename to ${old_name/AGILE_FLOW_/GEMBAFLOW_} (old name will be removed in a future release)" >&2
    export _GF_ENV_COMPAT_WARNED="${_GF_ENV_COMPAT_WARNED}:${old_name}"
}

# gf_env <new_var_name> <old_var_name> [default]
#
# Echo the value of <new_var_name> if set, else <old_var_name> if set
# (with a one-time deprecation warning), else [default] if provided,
# else empty. Always returns 0.
gf_env() {
    local new_name="$1"
    local old_name="$2"
    local default_value="${3:-}"

    # Indirect expansion — works on bash 3.2+ (macOS default).
    local new_value="${!new_name:-}"
    local old_value="${!old_name:-}"

    if [ -n "$new_value" ]; then
        printf '%s' "$new_value"
        return 0
    fi

    if [ -n "$old_value" ]; then
        _gf_env_warn_once "$old_name"
        printf '%s' "$old_value"
        return 0
    fi

    printf '%s' "$default_value"
    return 0
}

# Convenience wrappers for the three vars covered by Phase 2b. Keeping the
# defaults colocated here means callers do not repeat the magic strings.
gf_worker_account() {
    gf_env GEMBAFLOW_WORKER_ACCOUNT AGILE_FLOW_WORKER_ACCOUNT "va-worker"
}

gf_reviewer_account() {
    gf_env GEMBAFLOW_REVIEWER_ACCOUNT AGILE_FLOW_REVIEWER_ACCOUNT "va-reviewer"
}

gf_solo_mode() {
    gf_env GEMBAFLOW_SOLO_MODE AGILE_FLOW_SOLO_MODE ""
}

# gf_env_source_label <new_var_name> <old_var_name>
#
# Echo a human-readable label describing which env-var name supplied the
# value, e.g. "GEMBAFLOW_WORKER_ACCOUNT" or "AGILE_FLOW_WORKER_ACCOUNT (deprecated)".
# Used by doctor.sh to surface which name is in effect. Echoes "unset" if neither
# is set.
gf_env_source_label() {
    local new_name="$1"
    local old_name="$2"

    if [ -n "${!new_name:-}" ]; then
        printf '%s' "$new_name"
    elif [ -n "${!old_name:-}" ]; then
        printf '%s (deprecated)' "$old_name"
    else
        printf 'unset'
    fi
}
