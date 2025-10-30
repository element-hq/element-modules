ARG ELEMENT_VERSION=latest@sha256:6e91e641abe70dd02f1461b4f1ebf8f6807bfa381ec7f2c13e9e286c4e2b2918

FROM --platform=$BUILDPLATFORM node:lts-alpine@sha256:f36fed0b2129a8492535e2853c64fbdbd2d29dc1219ee3217023ca48aebd3787 AS builder

ARG BUILD_CONTEXT

RUN apk add --no-cache jq

WORKDIR /app
COPY package.json yarn.lock ./
# Copy the package.json files of all modules & packages to ensure the frozen workspace lockfile holds up
RUN --mount=type=bind,target=/docker-context \
    cd /docker-context/; \
    find . -path ./node_modules -prune -o -name "package.json" -mindepth 0 -maxdepth 4 -exec cp --parents "{}" /app/ \;
RUN yarn install --frozen-lockfile --ignore-scripts
COPY tsconfig.json ./
COPY ./$BUILD_CONTEXT ./$BUILD_CONTEXT
RUN cd $BUILD_CONTEXT && yarn vite build
RUN mkdir /modules
RUN cp -r ./$BUILD_CONTEXT/lib/ /modules/$(jq -r '"\(.name)-v\(.version)"' ./$BUILD_CONTEXT/package.json)

FROM ghcr.io/element-hq/element-web:${ELEMENT_VERSION}

COPY --from=builder /modules /modules/