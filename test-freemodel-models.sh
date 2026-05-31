#!/usr/bin/env bash

API_KEY="fe_oa_c912e1482a605ef9a0c0f03397263bdcca6796ac751ce41d"
BASE_URL="https://api.freemodel.dev/v1/chat/completions"

MODELS=(
  "gpt-5.4"
  "gpt-5.4-mini"
  "gpt-5.4-mini-2026-03-17"
  "claude-opus-4-7"
  "claude-sonnet-4-6"
  "claude-haiku-4-5-20251001"
  "deepseek-chat"
  "deepseek-reasoner"
)

for MODEL in "${MODELS[@]}"; do
  echo "Testing: $MODEL"

  RESPONSE=$(curl -s "$BASE_URL" \
    -H "Authorization: Bearer $API_KEY" \
    -H "Content-Type: application/json" \
    -d "{
      \"model\": \"$MODEL\",
      \"messages\": [
        {\"role\": \"user\", \"content\": \"Reply with OK only\"}
      ],
      \"max_tokens\": 20
    }")

  echo "$RESPONSE" | head -c 300
  echo
  echo "----------------------------"
done
