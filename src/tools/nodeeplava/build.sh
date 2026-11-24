#!/bin/sh
# SpypaperNoDeepLava.jar'ı derler. Paper API yerine yalnızca kullanılan sınıfların imza taslakları (stubs) kullanılır;
# jar'a taslaklar girmez, çalışırken gerçek Paper sınıfları kullanılır.
set -e
cd "$(dirname "$0")"
rm -rf out stubout && mkdir out stubout
javac --release 17 -d stubout $(find stubs -name '*.java')
javac --release 17 -cp stubout -d out src/dev/spypaper/nodeeplava/NoDeepLava.java
cp plugin.yml out/
(cd out && jar cf ../../../ui/assets/plugins/SpypaperNoDeepLava.jar plugin.yml dev)
rm -rf out stubout
