ARG DEBIAN_VERSION_NUMERIC=12

# Now copy it into our base image.
FROM gcr.io/distroless/base-nossl-debian${DEBIAN_VERSION_NUMERIC}:debug@sha256:eacaa3a43627a7936de63d04028b034f36f21b930cc6f50c4650d63f4672fed6 AS build

FROM gcr.io/distroless/base-nossl-debian${DEBIAN_VERSION_NUMERIC}

WORKDIR /src
COPY synapse_guest_module /src/synapse_guest_module
COPY --from=build /busybox/cp /bin/cp

CMD ["cp", "-r", "/src/synapse_guest_module", "/modules"]
