ARG PLAYWRIGHT_VERSION
FROM mcr.microsoft.com/playwright:v${PLAYWRIGHT_VERSION}-noble

WORKDIR /work

# fonts-dejavu is needed for the same RTL rendering as on CI
# socat is needed to forward host ports to chromium under the localhost origin
RUN apt-get update && apt-get -y install docker.io fonts-dejavu socat

# Install playwright at the right version in globals, this is useful for browserInDocker mode
RUN exec npx -y playwright@${PLAYWRIGHT_VERSION} run-server --help

COPY docker-entrypoint.sh /docker-entrypoint.sh

ENTRYPOINT ["/docker-entrypoint.sh"]
