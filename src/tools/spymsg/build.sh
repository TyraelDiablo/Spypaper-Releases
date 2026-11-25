#!/bin/sh
# SpypaperMessages.jar.ı derler.
# jar'a taslaklar girmez, çalışırken gerçek Paper sınıfları kullanılır.
set -e
cd "$(dirname "$0")"
rm -rf out stubout && mkdir out stubout
javac --release 17 -d stubout $(find stubs -name '*.java')
javac --release 17 -cp stubout -d out src/dev/spypaper/messages/SpypaperMessages.java
cp plugin.yml out/
(cd out && jar cf ../../../ui/assets/plugins/SpypaperMessages.jar plugin.yml dev)
rm -rf out stubout
