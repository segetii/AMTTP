# AMTTP Flutter Consumer App - Docker Image
# Builds Flutter web inside Docker and serves it via nginx.

FROM debian:bookworm-slim AS build

ARG FLUTTER_VERSION=3.38.9

RUN apt-get update && apt-get install -y --no-install-recommends \
	ca-certificates \
	curl \
	git \
	unzip \
	xz-utils \
	zip \
	&& rm -rf /var/lib/apt/lists/*

# Install Flutter SDK
RUN git clone --depth 1 --branch ${FLUTTER_VERSION} https://github.com/flutter/flutter.git /opt/flutter
ENV PATH="/opt/flutter/bin:/opt/flutter/bin/cache/dart-sdk/bin:${PATH}"

WORKDIR /app

# Copy only pubspec first for dependency caching
COPY pubspec.yaml pubspec.lock ./
RUN flutter config --enable-web
RUN flutter pub get

# Copy the rest and build
COPY . .
RUN flutter build web -t lib/main_consumer.dart --release


FROM nginx:alpine

COPY --from=build /app/build/web /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
