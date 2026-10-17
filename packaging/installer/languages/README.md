# Installer language source

`ChineseSimplified.isl` is the unmodified Simplified Chinese translation from
the Inno Setup source repository, apart from normalizing line endings to LF.

- Upstream: <https://github.com/jrsoftware/issrc>
- Fixed revision: `3cf18b4c969d4903fa55b20ecf09f803c1231d85`
- Source: <https://github.com/jrsoftware/issrc/blob/3cf18b4c969d4903fa55b20ecf09f803c1231d85/Files/Languages/ChineseSimplified.isl>
- Upstream Git blob: `d0d44258f51aa3127fc0d1167a7c8be328a9bdcf`
- License: `INNO-LICENSE.txt`, copied from the same upstream revision.
- Translation maintainer and attribution are retained in the language file.
- Supported message baseline: Inno Setup 6.5.0+.

The installer references this local file so a clean build does not depend on
which optional translations the compiler installation happens to include.
