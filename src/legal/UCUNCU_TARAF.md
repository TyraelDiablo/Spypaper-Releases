# Üçüncü Taraf Bildirimleri / Third-Party Notices

Spypaper, GNU GPL v3 ile lisanslanmış açık kaynak bir yazılımdır ([LICENSE.txt](LICENSE.txt)) ve aşağıdaki açık kaynak bileşenleri kullanır. Her bileşen kendi lisansına tabidir.

Spypaper is open-source software licensed under the GNU GPL v3 ([LICENSE.txt](LICENSE.txt)) and uses the following open-source components. Each is subject to its own license.

| Bileşen / Component | Lisans / License | Kaynak / Source |
|---|---|---|
| Python | Python Software Foundation License | https://www.python.org/ |
| Qt for Python (PySide6, Shiboken6) | GNU LGPL v3 | https://code.qt.io/cgit/pyside/pyside-setup.git/ |
| Qt 6 | GNU LGPL v3 | https://code.qt.io/ |
| nbtlib | MIT | https://github.com/vberlier/nbtlib |
| NumPy (nbtlib bağımlılığı / dependency) | BSD 3-Clause | https://github.com/numpy/numpy |
| psutil | BSD 3-Clause | https://github.com/giampaolo/psutil |
| PyYAML | MIT | https://github.com/yaml/pyyaml |
| segno (QR kodu / QR codes) | BSD 3-Clause | https://github.com/heuer/segno |
| python-soundfile (ses dönüştürme / audio conversion) | BSD 3-Clause | https://github.com/bastibe/python-soundfile |
| libsndfile (soundfile içinde / bundled with soundfile; Ogg, Vorbis, FLAC, Opus, mpg123, LAME dahil / incl.) | GNU LGPL v2.1 (+ BSD / LGPL bileşenler / components) | https://github.com/libsndfile/libsndfile |
| CFFI (soundfile bağımlılığı / dependency) | MIT | https://github.com/python-cffi/cffi |
| Lucide (arayüz ikonları / UI icons) | ISC | https://github.com/lucide-icons/lucide |
| Qt WebEngine (Chromium dahil / incl. Chromium) | GNU LGPL v3 + Chromium üçüncü taraf lisansları / third-party licenses | https://code.qt.io/cgit/qt/qtwebengine.git/ |
| PyInstaller bootloader | GPL v2 + bootloader exception | https://github.com/pyinstaller/pyinstaller |

## libsndfile (LGPL v2.1)

Spypaper, müzik disklerindeki sesi OGG'ye çevirmek için libsndfile'ı (python-soundfile ile birlikte gelen kitaplık) değiştirmeden, dinamik olarak kullanır. Kaynak kodu yukarıdaki adresten edinilebilir; kitaplığı kendi derlediğiniz bir sürümle değiştirebilirsiniz. LGPL v2.1: https://www.gnu.org/licenses/old-licenses/lgpl-2.1.html

Spypaper uses libsndfile (bundled with python-soundfile) unmodified via dynamic linking to convert music disc audio to OGG. Its source code is available at the address above, and you may replace it with your own build.

## Qt / PySide6 (LGPL v3)

Spypaper, Qt ve PySide6 kütüphanelerini değiştirmeden, dinamik olarak kullanır. LGPL v3 kapsamında:

- Bu kütüphanelerin kaynak kodu yukarıdaki adreslerden ücretsiz edinilebilir.
- Kütüphaneleri kendi değiştirdiğiniz sürümlerle değiştirme hakkınız vardır.
- LGPL v3 lisans metni: https://www.gnu.org/licenses/lgpl-3.0.html — GPL v3: https://www.gnu.org/licenses/gpl-3.0.html

Spypaper uses Qt and PySide6 unmodified via dynamic linking. Under the LGPL v3 you may obtain their source code from the addresses above and replace them with modified versions.

## MIT License (nbtlib, PyYAML, CFFI)

PyYAML: Copyright (c) 2017-2021 Ingy döt Net, Copyright (c) 2006-2016 Kirill Simonov
CFFI: Copyright (c) 2012-2025 Armin Rigo, Maciej Fijalkowski and others

```
Copyright (c) 2018 Valentin Berlier

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and
associated documentation files (the "Software"), to deal in the Software without restriction,
including without limitation the rights to use, copy, modify, merge, publish, distribute,
sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or
substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT
NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES
OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
```

## BSD 3-Clause License (psutil, NumPy, segno, python-soundfile)

```
psutil: Copyright (c) 2009, Jay Loden, Dave Daeschler, Giampaolo Rodola
NumPy:  Copyright (c) 2005-2025, NumPy Developers
segno:  Copyright (c) 2016 - 2025, Lars Heuer
python-soundfile: Copyright (c) 2013, Bastian Bechtold

Redistribution and use in source and binary forms, with or without modification, are permitted
provided that the following conditions are met:

 * Redistributions of source code must retain the above copyright notice, this list of conditions
   and the following disclaimer.
 * Redistributions in binary form must reproduce the above copyright notice, this list of
   conditions and the following disclaimer in the documentation and/or other materials provided
   with the distribution.
 * Neither the name of the copyright holder nor the names of its contributors may be used to
   endorse or promote products derived from this software without specific prior written
   permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR
IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND
FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR
CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER
IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF
THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
```

## Python Software Foundation License

Python, Python Software Foundation lisansıyla dağıtılır: https://docs.python.org/3/license.html

## Minecraft

Minecraft, Mojang Studios'un ticari markasıdır. Spypaper resmi bir Minecraft ürünü değildir; Mojang ya da Microsoft tarafından onaylanmamıştır ve onlarla bağlantılı değildir. Spypaper Minecraft'ın hiçbir dosyasını (oyun dosyaları, dil dosyaları, dokular) dağıtmaz; bu dosyalar kullanıcının kendi kurulumundan çıkarılır.

Minecraft is a trademark of Mojang Studios. Spypaper is not an official Minecraft product and is not approved by or associated with Mojang or Microsoft. Spypaper does not distribute any Minecraft files.

Paper, Purpur, Fabric, Forge ve NeoForge kendi geliştiricilerine aittir ve kendi lisanslarıyla dağıtılır; Spypaper bunları yalnızca kullanıcının isteğiyle resmi kaynaklarından indirir.

## ISC License (Lucide)

```
Copyright (c) for portions of Lucide are held by Cole Bemis 2013-2022 as part of Feather (MIT).
All other copyright (c) for Lucide are held by Lucide Contributors 2022.

Permission to use, copy, modify, and/or distribute this software for any purpose with or without fee
is hereby granted, provided that the above copyright notice and this permission notice appear in all copies.

THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES WITH REGARD TO THIS SOFTWARE
INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE
FOR ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM LOSS
OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING
OUT OF OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
```
