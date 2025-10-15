ARG ELEMENT_VERSION=latest@sha256:c9d5b12d8fb782beb5d48c73da1e14417bc06964e91d4d1847c04eef38cd3906

FROM --platform=$BUILDPLATFORM node:lts-alpine@sha256:dbcedd8aeab47fbc0f4dd4bffa55b7c3c729a707875968d467aaaea42d6225af AS builder

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