// https://github.com/docker/metadata-action#bake-definition
target "docker-metadata-action" {}

variable "ELEMENT_VERSION" {
  default = "latest"
}

group "default" {
  targets = ["element-web-modules", "element-web-modules-opendesk-plugin"]
}

target "_common" {
  inherits = ["docker-metadata-action"]
  platforms = [
    "linux/amd64",
    # "linux/arm64",
  ]
  context = "."
  args = {
    ELEMENT_VERSION = "${ELEMENT_VERSION}"
  }
}

target "element-web-modules" {
  inherits = ["_common"]
  context = "./packages/element-web-module-api"
  tag = "ghcr.io/element-hq/element-web-modules:latest"
}

target "module-base" {
  inherits = ["_common"]
  dockerfile = "./Dockerfile-bake-element-web-module"
  contexts = {
    "ghcr.io/element-hq/element-web-modules" = "target:element-web-modules",
  }
}

target "element-web-modules-opendesk-plugin" {
  inherits = ["module-base"]
  tag = "ghcr.io/element-hq/element-web-modules/opendesk-plugin:latest"
  args = {
    ELEMENT_VERSION = "${ELEMENT_VERSION}"
    BUILD_CONTEXT = "modules/opendesk/element-web"
  }
}