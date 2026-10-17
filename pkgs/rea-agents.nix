{
  lib,
  buildNpmPackage,
  fetchurl,
  nodejs_22,
  jq,
  autoPatchelfHook,
  stdenv,
}:
buildNpmPackage rec {
  pname = "rea-agents";
  version = "6.4.0";

  src = fetchurl {
    url = "https://registry.npmjs.org/rea-agents/-/rea-agents-${version}.tgz";
    hash = "sha256-WesWBLjbdfUi1Kl1w2zmtKKtRl5DutFl+aj3KDkdubg=";
  };

  nodejs = nodejs_22;
  npmDepsHash = "sha256-aMD66LEDaVjyDrdaaSQA2FjdAUltdj+RZH8W8xNIdNo=";
  nativeBuildInputs = [jq autoPatchelfHook];
  buildInputs = [stdenv.cc.cc.lib];

  # The published archive already includes the compiled runtime and skills.
  # Lock runtime dependencies only; source-tree development tools are unused.
  postPatch = ''
    ${jq}/bin/jq 'del(.devDependencies, .scripts)' package.json > package.json.tmp
    mv package.json.tmp package.json
    cp ${./rea-agents/package-lock.json} package-lock.json
  '';
  npmFlags = ["--ignore-scripts"];
  dontNpmBuild = true;
  dontNpmInstall = true;

  installPhase = ''
    runHook preInstall
    package_root="$out/lib/node_modules/rea-agents"
    mkdir -p "$package_root" "$out/bin"
    cp -R . "$package_root/"
    makeWrapper ${nodejs_22}/bin/node "$out/bin/rea" \
      --add-flags "$package_root/scripts/rea.mjs"
    ln -s rea "$out/bin/rea-agents"
    runHook postInstall
  '';

  meta = {
    description = "Reverse engineer applications with a CLI and MCP server";
    homepage = "https://rea.tools";
    license = lib.licenses.mit;
    mainProgram = "rea";
    platforms = lib.platforms.linux;
  };
}
