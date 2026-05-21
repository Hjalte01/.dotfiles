{
  lib,
  stdenvNoCC,
  fetchurl,
  makeWrapper,
  nodejs_22,
}:
stdenvNoCC.mkDerivation rec {
  pname = "codex-cli";
  version = "0.132.0";

  src = fetchurl {
    url = "https://registry.npmjs.org/@openai/codex/-/codex-${version}.tgz";
    hash = "sha512-OaTUz3oTbUP23I1yprQyaqO5LvlfWbTFIAI/JT2Hm0kgIsD+nKK14vauTzAt3zaeik6D7+meekCTuNdpU1dU2Q==";
  };

  codexLinuxX64 = fetchurl {
    url = "https://registry.npmjs.org/@openai/codex/-/codex-${version}-linux-x64.tgz";
    hash = "sha512-aGJPB+QkgtYQNQMlRGmE7oZstULu7k4trpux5r3CCZGPun4Xtwx3swtZXm7cWOVeTUkNfGCqdtCQ0bv6SKRiLA==";
  };

  nativeBuildInputs = [
    makeWrapper
  ];

  unpackPhase = ''
    runHook preUnpack

    mkdir -p source native
    tar -xzf "$src" --strip-components=1 -C source
    tar -xzf "$codexLinuxX64" --strip-components=1 -C native

    runHook postUnpack
  '';

  installPhase = ''
    runHook preInstall

    package_root="$out/lib/node_modules/@openai/codex"
    native_root="$package_root/node_modules/@openai/codex-linux-x64"

    mkdir -p "$package_root" "$native_root" "$out/bin"
    cp -R source/. "$package_root/"
    cp -R native/. "$native_root/"

    chmod +x "$native_root/vendor/x86_64-unknown-linux-musl/codex/codex"
    chmod +x "$native_root/vendor/x86_64-unknown-linux-musl/path/rg"
    chmod +x "$native_root/vendor/x86_64-unknown-linux-musl/codex-resources/bwrap"

    makeWrapper ${nodejs_22}/bin/node "$out/bin/codex" \
      --add-flags "$package_root/bin/codex.js"

    runHook postInstall
  '';

  meta = {
    description = "OpenAI Codex CLI";
    homepage = "https://www.npmjs.com/package/@openai/codex";
    license = lib.licenses.asl20;
    platforms = ["x86_64-linux"];
  };
}
