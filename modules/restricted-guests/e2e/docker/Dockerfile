# syntax=docker/dockerfile:1
# The image the tests, the mail sink and Element Web run in: Playwright with its
# Chromium, and a development build of Element Web with the restricted-guests
# module in /webapp. Element Web's source is the `element-web` build context.

FROM node:24-bookworm AS webapp
ARG PNPM_VERSION=12.11.2
RUN npm install -g pnpm@${PNPM_VERSION}
WORKDIR /src
COPY --from=element-web --exclude=.git --exclude=**/node_modules . .
RUN pnpm install --frozen-lockfile
ENV NX_DAEMON=false NX_NO_CLOUD=true
RUN ./node_modules/.bin/nx run-many -t build \
    -p @element-hq/web-shared-components @element-hq/element-web-module-api @element-hq/element-web-module-restricted-guests
RUN cd apps/web && NODE_OPTIONS=--max-old-space-size=4096 ./node_modules/.bin/webpack-cli --mode development
RUN mkdir -p apps/web/webapp/modules/restricted-guests && \
    cp modules/restricted-guests/lib/* apps/web/webapp/modules/restricted-guests/

FROM mcr.microsoft.com/playwright/python:v1.52.0-noble
COPY requirements.txt /tmp/
RUN pip install --no-cache-dir --break-system-packages -r /tmp/requirements.txt
COPY --from=webapp /src/apps/web/webapp /webapp
ENV GF_WEBAPP=/webapp HOME=/tmp
WORKDIR /e2e
