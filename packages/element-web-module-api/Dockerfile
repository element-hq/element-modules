ARG ELEMENT_VERSION=latest@sha256:6e38aeb4d30c6e6fd06db85dc20b07facfdad2de0312f352a1c35d516cdf7367

FROM --platform=$BUILDPLATFORM node:lts-alpine@sha256:d2166de198f26e17e5a442f537754dd616ab069c47cc57b889310a717e0abbf9 AS builder

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