# syntax=docker/dockerfile:1.4
# Base Python devcontainer - use bookworm to avoid bullseye Yarn GPG key issues
FROM mcr.microsoft.com/devcontainers/python:1-3.12-bookworm

USER root

# Remove broken Yarn repository that causes "NO_PUBKEY 62D54FD4003F6525" during apt-get update
# The base image includes Node/nvm with Yarn repo; the GPG key has expired
RUN rm -f /etc/apt/sources.list.d/yarn.list \
    /etc/apt/sources.list.d/nodesource.list \
    /etc/apt/sources.list.d/*yarn* \
    /etc/apt/sources.list.d/*nodesource* 2>/dev/null || true

# Verify apt works before features run
RUN apt-get update && rm -rf /var/lib/apt/lists/*

USER vscode
