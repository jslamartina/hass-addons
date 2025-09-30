#!/bin/bash

# Local Build for all architectures
docker run \
  --log-driver=json-file \
  --rm \
  --privileged \
  --volume ~/.docker:/root/.docker \
  --volume /my_addon:/data \
  ghcr.io/home-assistant/aarch64-builder:latest \
  --all \
  -t /data/cync-lan
