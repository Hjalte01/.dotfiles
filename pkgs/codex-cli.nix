{
  lib,
  stdenvNoCC,
  fetchurl,
  makeWrapper,
  nodejs_22,
}:
stdenvNoCC.mkDerivation rec {
  pname = "codex-cli";
  version = "0.135.0";

  src = fetchurl {
    url = "https://registry.npmjs.org/@openai/codex/-/codex-${version}.tgz";
    hash = "sha256-WK0X6witZFyWer/KojO+ORoL2kMvmzybz0xsZtC4+6c=";
  };

  codexLinuxX64 = fetchurl {
    url = "https://registry.npmjs.org/@openai/codex/-/codex-${version}-linux-x64.tgz";
    hash = "sha256-AVsBpU7TSVGQu6ORCWeRlJtoxg4PFHqIw4mgQsuqy78=";
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

    for executable in \
      "$native_root/vendor/x86_64-unknown-linux-musl/bin/codex" \
      "$native_root/vendor/x86_64-unknown-linux-musl/codex/codex" \
      "$native_root/vendor/x86_64-unknown-linux-musl/codex-path/rg" \
      "$native_root/vendor/x86_64-unknown-linux-musl/path/rg" \
      "$native_root/vendor/x86_64-unknown-linux-musl/codex-resources/bwrap" \
      "$native_root/vendor/x86_64-unknown-linux-musl/codex-resources/zsh/bin/zsh"; do
      if [ -e "$executable" ]; then
        chmod +x "$executable"
      fi
    done

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
