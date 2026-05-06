# Manticore Debug Notes — Issues Hit in Sessions 1-2

## Droplet Details
- Image: DigitalOcean vLLM 1-Click (Ubuntu 24.04 + ROCm)
- vLLM runs INSIDE a Docker container named `rocm` — NOT on the host
- Enter with: `docker exec -it rocm /bin/bash`
- vLLM logs: `docker exec rocm bash -c "tail -f /tmp/vllm.log"`

## vLLM Gotchas

### Starting vLLM
```bash
# From HOST (not inside rocm):
docker exec -d rocm bash -c "VLLM_ALLOW_LONG_MAX_MODEL_LEN=1 vllm serve Qwen/Qwen2.5-72B-Instruct --host 0.0.0.0 --port 8000 --max-model-len 65536 --enable-auto-tool-choice --tool-call-parser hermes &> /tmp/vllm.log"
```
- `max-model-len 131072` fails — model config enforces 65536 max
- Use `VLLM_ALLOW_LONG_MAX_MODEL_LEN=1` env var to unlock 65536
- `--enable-auto-tool-choice --tool-call-parser hermes` required for tool use in Messages API
- vLLM port 8000 is mapped from container to host — access at `localhost:8000` from host

### Checking vLLM
```bash
curl http://localhost:8000/v1/models      # Should return Qwen model info
docker exec rocm bash -c "tail -20 /tmp/vllm.log"
docker exec rocm bash -c "ps aux | grep vllm | grep -v grep"
```

### vLLM Messages API Hanging
- Symptom: `/v1/models` works, `/v1/messages` hangs indefinitely
- Cause: previous requests clogged the queue (zombie requests from failed runs)
- Fix: kill and restart vLLM
```bash
docker exec rocm bash -c "pkill -f 'vllm serve'"
sleep 5
# Then start again
```

## Shannon / Manticore Gotchas

### Root User Check
Shannon blocks running as root. Fix in compiled CLI:
```bash
LINE=$(grep -n "isRoot" /root/manticore/apps/cli/dist/index.mjs | grep "geteuid" | cut -d: -f1 | head -1)
sed -i "${LINE}s/.*/const isRoot = false;/" /root/manticore/apps/cli/dist/index.mjs
```

### .env File (CRITICAL — all 6 vars required)
```
ANTHROPIC_BASE_URL=http://host.docker.internal:8000/v1
ANTHROPIC_AUTH_TOKEN=placeholder
ANTHROPIC_SMALL_MODEL=Qwen/Qwen2.5-72B-Instruct
ANTHROPIC_MEDIUM_MODEL=Qwen/Qwen2.5-72B-Instruct
ANTHROPIC_LARGE_MODEL=Qwen/Qwen2.5-72B-Instruct
CLAUDE_CODE_MAX_OUTPUT_TOKENS=8000
```
- Missing ANTHROPIC_SMALL_MODEL → preflight fails with "claude-haiku-4-5-20251001 does not exist"
- Must NOT have ANTHROPIC_API_KEY alongside ANTHROPIC_AUTH_TOKEN → "Multiple providers detected" error
- Shell env vars override .env — unset any conflicting vars: `unset ANTHROPIC_API_KEY`

### "Multiple providers detected" Error
```bash
# Check what's exported in shell:
env | grep ANTHROPIC
# Clear all, let .env be the only source:
unset ANTHROPIC_API_KEY ANTHROPIC_AUTH_TOKEN ANTHROPIC_BASE_URL ANTHROPIC_MEDIUM_MODEL ANTHROPIC_LARGE_MODEL ANTHROPIC_SMALL_MODEL
```

### Worker Container Entrypoint Crash (GID 0 conflict)
- Symptom: `docker logs <worker>` shows only `groupadd: GID '0' already exists` — nothing else
- Cause: Running as root (UID=0), entrypoint tries to `groupadd -g 0 pentest` but GID 0 is reserved
- Fix: Already applied in `entrypoint.sh` — skip UID remapping when TARGET_UID=0

### Preflight Validation Bypass (preflight.ts)
Shannon validates credentials by making a live API call before agents run.
vLLM rejects this. Bypass in `apps/worker/src/services/preflight.ts`:
```typescript
// At the start of validateCredentials function, before any API calls:
if (process.env.ANTHROPIC_BASE_URL && process.env.ANTHROPIC_AUTH_TOKEN) {
  logger.info('Custom base URL OK');
  return ok(undefined);
}
```
After changing: `pnpm build` then `./manticore build`

### DVWA as Shannon Target
- DVWA source is PHP files — need to copy from container and init git:
```bash
docker cp dvwa:/var/www/html /root/dvwa-src
cd /root/dvwa-src && git init && git add -A && git commit -m "dvwa source"
```
- Run scan with: `./manticore start -u http://host.docker.internal:8080 -r /root/dvwa-src -w dvwa-scan`
- Shannon analyzes the SOURCE CODE at -r path, not the live site

## Networking
- Worker container is on `shannon-net` Docker network
- Use `host.docker.internal` to reach host ports from inside worker container
- `ANTHROPIC_BASE_URL` must use `host.docker.internal`, not `localhost`
- DVWA port 8080 needs UFW rule: `ufw allow 8080`

## Pending Issue (Session 2 end)
Shannon pre-recon fails in ~400ms: "Invalid request: There's an issue with the selected model (Qwen/Qwen2.5-72B-Instruct)"
- vLLM /v1/messages endpoint responds to simple curl but hangs under load
- Suspected cause: vLLM queue clogged from previous failed runs
- Next step: restart vLLM completely, test messages API fresh, then rerun scan
- Fallback: add LiteLLM proxy to translate Anthropic format → OpenAI format for vLLM
