IMAGE=dtdemos/llm-load-generator
VERSION=v1.1.0

build:
	docker build -t $(IMAGE):$(VERSION) .

buildx:
	docker buildx build --platform linux/amd64,linux/arm64 -t ${IMAGE}:${VERSION} .

push:
	docker push $(IMAGE):$(VERSION)

login:
	docker logout && docker login
