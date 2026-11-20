#!/usr/bin/env bash
# Checks tools and which keys are set. Never prints key values.
cd "$(dirname "$0")/.."
ok()   { printf "  \033[32m✓\033[0m %s\n" "$1"; }
bad()  { printf "  \033[31m✗\033[0m %s\n" "$1"; }

echo "Tools"
if command -v node >/dev/null; then
  v=$(node -v | sed 's/v//; s/\..*//')
  [ "$v" -ge 22 ] && ok "node $(node -v)" || bad "node $(node -v) (Senso/Guild CLIs need 22+)"
else bad "node missing"; fi
if command -v python3 >/dev/null; then ok "$(python3 --version)"; else bad "python3 missing"; fi
for t in git gh claude; do command -v $t >/dev/null && ok "$t" || bad "$t missing"; done
gh auth status >/dev/null 2>&1 && ok "gh logged in" || bad "gh not logged in (gh auth login)"
git ls-remote origin >/dev/null 2>&1 && ok "repo access" || bad "can't reach repo (accept the GitHub invite?)"

echo "Keys (.env)"
if [ -f .env ]; then
  set -a; . ./.env; set +a
  for k in ANTHROPIC_API_KEY SENSO_API_KEY FIREDRILL_API_KEY GUILD_API_KEY LLM_API_KEY SIE_API_KEY ARCEE_API_KEY SINGLESTORE_URL; do
    [ -n "${!k}" ] && ok "$k set" || printf "  · %s not set\n" "$k"
  done
  if [ -n "$SENSO_API_KEY" ]; then
    code=$(curl -s -o /dev/null -w '%{http_code}' -H "X-API-Key: $SENSO_API_KEY" https://apiv2.senso.ai/api/v1/org/me)
    [ "$code" = 200 ] && ok "Senso key works" || bad "Senso key returned HTTP $code"
  fi
else
  bad "no .env (cp .env.example .env)"
fi
