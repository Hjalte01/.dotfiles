{
  lib,
  writeShellApplication,
  python3,
  ffmpeg,
  handy,
  dictation,
  dictation-live ? null,
}:
writeShellApplication {
  name = "dictation-benchmark";
  runtimeInputs = [python3 ffmpeg dictation] ++ lib.optional (dictation-live != null) dictation-live;
  text = ''
    export DICTATION_BENCHMARK_HANDY=${handy}/bin/handy
    exec python3 ${../scripts/dictation-benchmark.py} "$@"
  '';
  meta = {
    description = "Silent English/Danish dictation speed and word-error benchmarks";
    license = lib.licenses.mit;
    platforms = lib.platforms.linux;
  };
}
