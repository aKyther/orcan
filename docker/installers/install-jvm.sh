#!/usr/bin/env bash
# One component per build stage. Version/input changes do not rebuild siblings.
set -Eeuo pipefail
component="$1" enabled="$2" version="$3" destination="$4"
case "$component" in jdk|gradle|maven|kotlin|scala|sbt) ;; *) exit 2 ;; esac
[[ "$enabled" == 0 || "$enabled" == 1 ]] || exit 2
[[ "$version" =~ ^[0-9]+([.][0-9]+){0,3}([-+][A-Za-z0-9.-]+)?$ ]] || exit 2
mkdir -p "$destination"
[[ "$enabled" == 1 ]] || exit 0
temporary="$(mktemp -d)"
trap 'rm -rf "$temporary"' EXIT
case "$(dpkg --print-architecture)" in
    amd64) jdk_arch=x64; sbt_other_arch=aarch64 ;;
    arm64) jdk_arch=aarch64; sbt_other_arch=x86_64 ;;
    *) exit 2 ;;
esac
case "$component" in
    jdk)
        curl -fsSL "https://api.adoptium.net/v3/binary/latest/${version}/ga/linux/${jdk_arch}/jdk/hotspot/normal/eclipse" \
            | tar -xz -C "$destination" --strip-components=1
        "$destination/bin/java" -version
        ;;
    maven)
        curl -fsSL "https://archive.apache.org/dist/maven/maven-3/${version}/binaries/apache-maven-${version}-bin.tar.gz" \
            | tar -xz -C "$destination" --strip-components=1
        ;;
    scala)
        curl -fsSL "https://github.com/scala/scala3/releases/download/${version}/scala3-${version}.tar.gz" \
            | tar -xz -C "$destination" --strip-components=1
        ;;
    sbt)
        curl -fsSL "https://github.com/sbt/sbt/releases/download/v${version}/sbt-${version}.tgz" \
            | tar -xz -C "$destination" --strip-components=1 \
                --exclude="sbt/bin/sbtn-${sbt_other_arch}-pc-linux" \
                --exclude='sbt/bin/sbtn-*-apple-darwin' --exclude='sbt/bin/sbtn-*-pc-win32.exe'
        ;;
    gradle|kotlin)
        if [[ "$component" == gradle ]]; then
            url="https://services.gradle.org/distributions/gradle-${version}-bin.zip"
            folder="gradle-${version}"
        else
            url="https://github.com/JetBrains/kotlin/releases/download/v${version}/kotlin-compiler-${version}.zip"
            folder=kotlinc
        fi
        curl -fsSL "$url" -o "$temporary/archive.zip"
        unzip -q "$temporary/archive.zip" -d "$temporary"
        cp -a "$temporary/$folder/." "$destination/"
        ;;
esac
