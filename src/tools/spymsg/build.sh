#!/bin/sh
# SpypaperMessages.jar.ı derler.
# Bot motoru (BotEngine) Paper'ın iç sınıflarıyla derlenir: PAPER_CP, Paper sunucusunun jar'larını
# (versions/<sürüm>/paper-<sürüm>.jar, libraries/... ) içeren sınıf yolu olmalı. Bu jar'lar depoya girmez.
# Paper 26+ sınıfları Java 25 sürümündedir; JDK 21 ile derlerken önce sürüm baytlarını 65'e çeken kopyalar
# kullanılabilir (yalnızca derleme için; jar'a girmez).
set -e
cd "$(dirname "$0")"
[ -n "$PAPER_CP" ] || { echo "PAPER_CP gerekli"; exit 1; }
rm -rf out && mkdir out
javac --release 21 -proc:none -cp "$PAPER_CP" -d out $(find src -name '*.java')
cp plugin.yml out/
printf 'Manifest-Version: 1.0\npaperweight-mappings-namespace: mojang\n' > out/MANIFEST.MF
(cd out && jar cfm ../../../ui/assets/plugins/SpypaperMessages.jar MANIFEST.MF plugin.yml dev)
rm -rf out
