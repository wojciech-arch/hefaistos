# Sourced by the scripts: loads KEY=value lines from the repo's .env without overriding
# variables already set in the environment.
load_env() {
  [ -f "$1" ] || return 0
  while IFS='=' read -r key value; do
    case "$key" in ''|\#*) continue ;; esac
    if [ -z "$(printenv "$key" || true)" ]; then export "$key=$value"; fi
  done < "$1"
}
