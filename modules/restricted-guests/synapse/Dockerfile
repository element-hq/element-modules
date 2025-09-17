ARG DEBIAN_VERSION_NUMERIC=12

# Now copy it into our base image.
FROM gcr.io/distroless/base-nossl-debian${DEBIAN_VERSION_NUMERIC}:debug@sha256:1a14fd3ffe3745e5523faa1740904dfd851c324957e230ea2db31601e2f537ec AS build

FROM gcr.io/distroless/base-nossl-debian${DEBIAN_VERSION_NUMERIC}

WORKDIR /src
COPY synapse_guest_module /src/synapse_guest_module
COPY --from=build /busybox/cp /bin/cp

CMD ["cp", "-r", "/src/synapse_guest_module", "/modules"]
